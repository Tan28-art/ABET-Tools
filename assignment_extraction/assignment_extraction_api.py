from collections import defaultdict
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
        time.sleep(0.2)  # To avoid hitting rate limits
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
    
def extract_rubric_assessment_data(submission):
    """Extracts and anonymizes rubric assessment data from a submission."""
    rubric_data = submission.get('rubric_assessment', {})
    if not rubric_data:
        return None
    return {
        cid: {'points': data.get('points'), 'comments': data.get('comments', '')}
        for cid, data in rubric_data.items()
    }

def find_abet_outcomes(all_assignments: list[dict]) -> tuple[defaultdict, dict]:
    """Scans assignments, groups them by ABET outcome, and extracts outcome details."""
    outcome_map = defaultdict(list)
    outcome_details = {}  # Store title, description, and long_description for each outcome
    for assign in all_assignments:
        if not (rubric := assign.get("rubric")): continue
        for criterion in rubric:
            # We check the main 'description' for the ABET tag
            if "abet" in criterion.get("description", "").lower() and (oid := criterion.get("outcome_id")):
                outcome_map[oid].append(assign)
                if oid not in outcome_details:
                    # Use 'description' for the title and main outcome text
                    title_description = criterion.get("description", "").strip()
                    long_description = criterion.get("long_description", "").strip()
                    clean_title = re.sub(r'<[^>]+>', '', title_description).strip()
                    
                    outcome_details[oid] = {
                        "title": clean_title,
                        "full_description": title_description,
                        "long_description": long_description
                    }
    return outcome_map, outcome_details

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
    for sub, label in [(highest, "highest_graded"), (lowest, "lowest_graded")]:
        if not (sub and sub.get("attachments")): continue

        attachment = sub["attachments"][0]
        ext = os.path.splitext(attachment.get("filename", ""))[1]
        generic_filename = f"{label}_submission{ext}"
        
        if download_file(attachment["url"], os.path.join(local_path, generic_filename)):
            saved_files.append(os.path.join(local_path, generic_filename))

        # Create anonymized metadata JSON
        metadata_path = os.path.join(local_path, f"{label}_details.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump({
                'score': sub.get('score'),
                'points_possible': assignment.get('points_possible'),
                'original_filename': attachment.get("filename"),
                'rubric_assessment': extract_rubric_assessment_data(sub)
            }, f, indent=2)
        saved_files.append(metadata_path)
    return saved_files


def upload_files_to_canvas(course_id, folder_path, file_paths):
    """
    Uploads a list of local files to a specific folder in Canvas, overwriting any existing files.

    Args:
        course_id (str): The ID of the destination Canvas course.
        folder_path (str): The target folder path within the course's "Files" section.
        file_paths (list): A list of local paths to the files to be uploaded.
    """
    # Will try to upload each file up to MAX_RETRIES times
    MAX_RETRIES = 3
    
    print(f"Uploading {len(file_paths)} files to Canvas folder '{folder_path}'...")
    for file_path in file_paths:
        for attempt in range(MAX_RETRIES):
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
                break
            except Exception as e:
                    print(f"  - ERROR on attempt {attempt + 1}/{MAX_RETRIES} for {filename}: {e}")
                    if attempt < MAX_RETRIES - 1:
                        print("    Retrying in 2 seconds...")
                        time.sleep(2)  # Wait before retrying
                    else:
                        print(f"  - All {MAX_RETRIES} attempts failed for {filename}. Giving up.")
        
        time.sleep(1)  # Pause to avoid hitting rate limits
            
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
    header = ['score', 'submitted_at', 'workflow_state']

    with open(report_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for sub in submissions:
            user = sub.get('user', {})
            writer.writerow([
                user.get('id', 'N/A'), user.get('name', 'N/A'),
                sub.get('score', ''), sub.get('submitted_at', 'N/A'),
                sub.get('workflow_state', 'N/A')
            ])
    print(f"  - Grade report saved to {report_path}")
    return report_path

def generate_outcome_reports(grades_fetcher, outcome_map, outcome_details, course_info, semester_code):
    """Generates and uploads a rich JSON summary report for each ABET outcome."""
    print("\nGenerating Rich ABET Outcome JSON Reports")
    local_reports_to_upload = []
    
    for outcome_id, assignments in outcome_map.items():
        all_outcome_submissions = []
        contributing_assignments = []

        for assign in assignments:
            submissions = grades_fetcher.fetch_assignment_submissions(SOURCE_COURSE_ID, assign['id'])
            graded_subs = [s for s in submissions if s.get('score') is not None]
            
            points_possible = assign.get('points_possible') or 1
            for s in graded_subs:
                s['points_possible_for_calc'] = points_possible
            all_outcome_submissions.extend(graded_subs)
            
            scores = [s['score'] for s in graded_subs]
            
            # Create a copy of the full assignment object from Canvas
            assignment_data = assign.copy()
            # Add a new key with our calculated assessment statistics
            assignment_data['assessment_stats'] = {
                "sample_size": len(scores),
                "average_score": sum(scores) / len(scores) if scores else 0
            }
            contributing_assignments.append(assignment_data)
        
        if not all_outcome_submissions: continue

        num_competent = sum(1 for s in all_outcome_submissions if (s['score'] / s['points_possible_for_calc']) >= 0.7)
        total_graded = len(all_outcome_submissions)
        percent_competent = (num_competent / total_graded) * 100 if total_graded else 0
        outcome_info = outcome_details.get(outcome_id, {})

        report_data = {
            "outcome_title": outcome_info.get("title", "Unknown Outcome"),
            "outcome_full_description": outcome_info.get("full_description", ""),
            "outcome_long_description": outcome_info.get("long_description", ""),
            "course_info": course_info,  # Dumps the entire course info object
            "assessment_summary": {
                "total_students_assessed": total_graded,
                "number_competent": num_competent,
                "percent_competent": round(percent_competent, 2),
                "outcome_met": percent_competent >= 70.0
            },
            "contributing_assignments": contributing_assignments
        }
        
        title_str = outcome_info.get("title", f"Outcome_{outcome_id}")
        match = re.search(r'(CS|CSE)\s*ABET\s*\d+', title_str, re.IGNORECASE)
        clean_name = match.group(0).replace(' ', '_') if match else re.sub(r'[^\\w-]', '_', title_str)
        report_filename = f"OUTCOME_{clean_name}.json"

        report_path = os.path.join(TEMP_DIR, report_filename)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=4)
        local_reports_to_upload.append(report_path)

    if local_reports_to_upload:
        canvas_folder = f"{semester_code}/_ABET_Outcome_Reports"
        upload_files_to_canvas(DESTINATION_COURSE_ID, canvas_folder, local_reports_to_upload)

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

    course_info = api_request(f"courses/{SOURCE_COURSE_ID}", params={"include[]": "syllabus_body"})
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
            
    # Outcome folders
    outcome_map, outcome_details = find_abet_outcomes(abet_assignments)
    if outcome_map:
        generate_outcome_reports(grades_fetcher, outcome_map, outcome_details, course_info, semester_year_code)
    else:
        print("\nNo assignments with rubric outcomes found for summary report generation.")

    shutil.rmtree(TEMP_DIR)
    print("\nProcess finished.")


if __name__ == "__main__":
    main()
