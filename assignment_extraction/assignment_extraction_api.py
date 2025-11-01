import csv
import time
import requests
import json
import os
import re
import shutil
from urllib.parse import urljoin
from fetch_grades import CanvasGradesFetcher

# CONFIGURATION
CANVAS_DOMAIN = "canvas.asu.edu"
CANVAS_TOKEN = os.getenv("canvas_access_token")
SOURCE_COURSE_ID = "240102"
DESTINATION_COURSE_ID = "240102"
ABET_TAG = "abet" # Since the abet rubric will always have abet, we can search for this tag to identify relevant assignments

# SETUP
API_BASE_URL = f"https://{CANVAS_DOMAIN}/api/v1/"
HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
TEMP_DIR = "temp_assignment_files"


def api_request(url, method="GET", params=None, data=None, stream=False):
    """
    Performs a single, non-paginated API request to the Canvas LMS.

    Args:
        url (str): The API endpoint or a full URL.
        method (str, optional): The HTTP method (e.g., 'GET', 'POST'). Defaults to 'GET'.
        params (dict, optional): URL parameters for the request. Defaults to None.
        data (dict, optional): The payload for POST/PUT requests. Defaults to None.
        stream (bool, optional): If True, the response is streamed for file downloads. Defaults to False.

    Returns:
        dict or requests.Response or None: The JSON response, a Response object for streams,
        or None if an error occurs.
    """
    if not url.startswith("https://"):
        url = urljoin(API_BASE_URL, url)
    try:
        response = requests.request(
            method, url, headers=HEADERS, params=params, data=data, stream=stream
        )
        response.raise_for_status()
        if stream:
            return response
        return response.json() if response.text else {"status": "success"}
    except requests.exceptions.RequestException as e:
        print(
            f"API Error on {method} {url}: {e}\nResponse: {e.response.text if e.response else 'N/A'}"
        )
        return None


def get_paginated_list(endpoint, params=None):
    """
    Retrieves a complete list of items from a paginated Canvas API endpoint.

    Args:
        endpoint (str): The API endpoint to query (e.g., 'courses/123/assignments').
        params (dict, optional): Initial URL parameters. Defaults to None.

    Returns:
        list: A list containing all items retrieved from all pages.
    """
    all_items = []
    url = urljoin(API_BASE_URL, endpoint)
    params = params or {}
    params["per_page"] = 100

    while url:
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            all_items.extend(response.json())

            url = None  # Assume no next page unless found
            if "Link" in response.headers:
                links = requests.utils.parse_header_links(response.headers["Link"])
                for link in links:
                    if link.get("rel") == "next":
                        url = link["url"]
            params = None  # Next URL from Canvas already contains all parameters
        except requests.exceptions.RequestException as e:
            print(
                f"API Error on GET {url}: {e}\nResponse: {e.response.text if e.response else 'N/A'}"
            )
            break

    return all_items


def find_abet_assignments(course_id):
    """
    Finds all ABET-related assignments in a course by searching names and rubrics.

    Args:
        course_id (str): The ID of the Canvas course to search within.

    Returns:
        list: A list of assignment objects that match the ABET criteria.
    """
    print(f"Searching for ABET assignments in course {course_id}...")
    endpoint = f"courses/{course_id}/assignments"
    assignments = get_paginated_list(endpoint, params={"include[]": "rubric"})

    return [
        a
        for a in assignments
        if ABET_TAG in a.get("name", "").lower()
        or any(
            ABET_TAG in r.get("description", "").lower() for r in a.get("rubric", [])
        )
    ]


def get_extreme_submissions(course_id, assignment_id):
    """
    Fetches all submissions for an assignment and returns the highest and lowest graded.

    Args:
        course_id (str): The ID of the course.
        assignment_id (int): The ID of the assignment.

    Returns:
        tuple: A tuple containing the highest and lowest graded submission objects, or (None, None).
    """
    endpoint = f"courses/{course_id}/assignments/{assignment_id}/submissions"
    submissions = get_paginated_list(endpoint, params={"include[]": "user"}) # get all submissions with user info

    if not submissions:
        return None, None

    graded = sorted(
        [
            s
            for s in submissions
            if s.get("workflow_state") == "graded" and s.get("score") is not None
        ],
        key=lambda s: s["score"],
    )

    return (graded[-1], graded[0]) if graded else (None, None) # return highest and lowest


def download_file(url, local_path):
    """
    Downloads a file from a URL to a local path using a streamed response.

    Args:
        url (str): The URL of the file to download.
        local_path (str): The local path where the file will be saved.

    Returns:
        bool: True if the download was successful, False otherwise.
    """
    # Python shutil: https://docs.python.org/3/library/shutil.html#shutil.copyfileobj
    try:
        with api_request(url, stream=True) as r, open(local_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)
        return True
    except Exception as e:
        print(f"  - Failed to download from {url}: {e}")
        return False


def extract_and_save_artifacts(assignment):
    """
    Saves all relevant artifacts for an assignment to a local temporary directory.
    This includes the description, rubric, any documents attached in the description,
    and files from the highest and lowest graded student submissions.

    Args:
        assignment (dict): The assignment object.

    Returns:
        list: A list of local file paths for all successfully saved artifacts.
    """
    assignment_name = f"{assignment['id']}_{assignment['name'].replace(' ', '_')}"
    local_path = os.path.join(TEMP_DIR, assignment_name)
    os.makedirs(local_path, exist_ok=True)

    saved_files = []

    if description := assignment.get("description"):
        path = os.path.join(local_path, "description.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(description)
        saved_files.append(path)

        file_ids = re.findall(r"/files/(\d+)", description)
        for file_id in set(file_ids):
            file_info = api_request(f"files/{file_id}")
            if file_info and download_file(
                file_info["url"], os.path.join(local_path, file_info["filename"])
            ):
                saved_files.append(os.path.join(local_path, file_info["filename"]))

    if rubric := assignment.get("rubric"):
        path = os.path.join(local_path, "rubric.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rubric, f, indent=4)
        saved_files.append(path)

    highest, lowest = get_extreme_submissions(assignment["course_id"], assignment["id"])
    for sub, label in [(highest, "highest"), (lowest, "lowest")]:
        if not (sub and sub.get("attachments")):
            continue
        # We need to get student name and id
        user = sub.get("user", {})
        student_id = user.get("id", "UnknownID")

        for i, attachment in enumerate(sub.get("attachments", [])):
            original_filename = attachment.get("filename", "file")
            file_extension = os.path.splitext(original_filename)[1]
            
            # Create a generic, numbered filename to handle multiple attachments and preserve the extension
            generic_filename = f"{label}_submission{file_extension}"
            
            # Create a corresponding metadata file
            metadata_filename = f"{label}_submission_details.json"
            metadata_path = os.path.join(local_path, metadata_filename)
            
            student = sub.get('user', {})
            student_obj = {
                'id': student_id,
                'name': student.get('name', 'N/A'),
            }
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'score': sub.get('score'),
                    'student': student_obj,
                    'original_filename': original_filename
                }, f, indent=2)
            saved_files.append(metadata_path)

            if download_file(attachment["url"], os.path.join(local_path, generic_filename)):
                saved_files.append(os.path.join(local_path, generic_filename))

    return saved_files


def upload_files_to_canvas(course_id, folder_path, file_paths):
    """
    Uploads a list of local files to a specific folder in Canvas, overwriting any existing files.

    Args:
        course_id (str): The ID of the destination Canvas course.
        folder_path (str): The target folder path within the course's "Files" section.
        file_paths (list): A list of local paths to the files to be uploaded.
    """
    print(f"Uploading {len(file_paths)} files to Canvas folder '{folder_path}'...")
    for file_path in file_paths:
        try:
            filename = os.path.basename(file_path)
            # Add 'on_duplicate': 'overwrite' to replace existing files.
            init_data = {
                "name": filename,
                "parent_folder_path": folder_path,
                "on_duplicate": "overwrite",
            }
            upload_info = api_request(
                f"courses/{course_id}/files", "POST", data=init_data
            )
            if not upload_info:
                continue

            with open(file_path, "rb") as f:
                upload_response = requests.post(
                    upload_info["upload_url"],
                    data=upload_info["upload_params"],
                    files={"file": f},
                )
                upload_response.raise_for_status()

            if confirmation := upload_response.json():
                api_request(confirmation["location"], "GET")
            print(f"  - Successfully uploaded {filename}")
        except Exception as e:
            print(f"  - Failed to upload {filename}: {e}")
        
        time.sleep(0.5)  # Pause to avoid hitting rate limits
            
def generate_assignment_grade_report(grades_fetcher, assignment, local_path):
    """
    Creates a detailed CSV grade report for a single assignment.

    Args:
        grades_fetcher (CanvasGradesFetcher): The fetcher instance to get data.
        assignment (dict): The assignment object.
        local_path (str): The local directory to save the report in.

    Returns:
        str or None: The file path to the generated CSV, or None if no submissions exist.
    """
    print("  - Generating detailed grade report...")
    submissions = grades_fetcher.fetch_assignment_submissions(assignment['course_id'], assignment['id'])
    if not submissions:
        print("  - No submissions found for this assignment.")
        return None

    report_path = os.path.join(local_path, f"grade_report_{assignment['id']}.csv")
    header = ['student_id', 'student_name', 'score', 'submitted_at', 'workflow_state']

    with open(report_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for sub in submissions:
            user = sub.get('user', {})
            writer.writerow([
                user.get('id', 'N/A'),
                user.get('name', 'N/A'),
                sub.get('score', ''),
                sub.get('submitted_at', 'N/A'),
                sub.get('workflow_state', 'N/A')
            ])
    print(f"  - Detailed grade report saved to {report_path}")
    return report_path

# Steps Overview:
# 1. Setup: Clean and create a temporary directory for file storage.
# 2. Find: Identify all target assignments.
# 3. Process Loop: For each assignment, extract all artifacts locally.
# 4. Upload: Push the collected local files to a structured folder in Canvas.
# 5. Teardown: Clean up the temporary directory.
def main():
    """Main process to find, extract, and store ABET assignment data."""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)
    
    grades_fetcher = CanvasGradesFetcher()

    course_info = api_request(f"courses/{SOURCE_COURSE_ID}")
    course_name = course_info.get("name") if course_info.get("name") else course_info.get("course_code", "UnknownCourse").replace(" ", "_")
    semester_year_code = f"Fall_2025_{course_name}"
    
    print("\nProcessing: Generating Course-Wide Grade Reports")
    grade_report_files = grades_fetcher.generate_grade_reports(int(SOURCE_COURSE_ID), TEMP_DIR)
    if grade_report_files:
        grades_canvas_folder = f"{semester_year_code}/_Course_Grade_Reports"
        upload_files_to_canvas(DESTINATION_COURSE_ID, grades_canvas_folder, list(grade_report_files))
    else:
        print("Could not generate course-wide grade reports.")

    abet_assignments = find_abet_assignments(SOURCE_COURSE_ID)
    if not abet_assignments:
        print("No ABET-tagged assignments found.")
        return

    print(f"\nFound {len(abet_assignments)} ABET assignments to process.")
    for assignment in abet_assignments:
        print(f"\nProcessing: {assignment['name']} ")

        local_files = extract_and_save_artifacts(assignment)
        assignment_folder_path = os.path.join(TEMP_DIR, f"{assignment['id']}_{assignment['name'].replace(' ', '_')}")
        assignment_report_path = generate_assignment_grade_report(grades_fetcher, assignment, assignment_folder_path)

        if assignment_report_path:
            local_files.append(assignment_report_path)
            
        if local_files:
            canvas_folder = (
                f"{semester_year_code}/{assignment['name'].replace(' ', '_')}"
            )
            upload_files_to_canvas(DESTINATION_COURSE_ID, canvas_folder, local_files)
        else:
            print("No artifacts found to upload for this assignment.")

    shutil.rmtree(TEMP_DIR)
    print("\nProcess finished.")


if __name__ == "__main__":
    main()
