import requests
import json
import os
import re
import shutil
from urllib.parse import urljoin

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
    submissions = get_paginated_list(endpoint)

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

    return (graded[-1], graded[0]) if graded else (None, None)


def download_file(url, local_path):
    """
    Downloads a file from a URL to a local path using a streamed response.

    Args:
        url (str): The URL of the file to download.
        local_path (str): The local path where the file will be saved.

    Returns:
        bool: True if the download was successful, False otherwise.
    """
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
        for attachment in sub.get("attachments", []):
            filename = f"{label}_grade_{sub['score']}_{attachment['filename']}"
            if download_file(attachment["url"], os.path.join(local_path, filename)):
                saved_files.append(os.path.join(local_path, filename))

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

    course_info = api_request(f"courses/{SOURCE_COURSE_ID}")
    semester_year_code = f"Fall_2025_{course_info.get('name', 'UnknownCourse')}"

    abet_assignments = find_abet_assignments(SOURCE_COURSE_ID)
    if not abet_assignments:
        print("No ABET-tagged assignments found.")
        return

    print(f"\nFound {len(abet_assignments)} ABET assignments to process.")
    for assignment in abet_assignments:
        print(f"\nProcessing: {assignment['name']} ")

        local_files = extract_and_save_artifacts(assignment)

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
