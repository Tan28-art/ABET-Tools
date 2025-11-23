from collections import defaultdict
import csv
import io
import time
import requests
import json
import os
import re
import shutil
from urllib.parse import urljoin
from fetch_grades import CanvasGradesFetcher
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Query
from typing import Annotated
import PyPDF2
import docx
from csv_filter import parse_roster_for_major_map, is_cs_or_cse
from typing import Optional
from xhtml2pdf import pisa

app = FastAPI()

# CONFIGURATION
CANVAS_DOMAIN = "canvas.asu.edu"
ABET_TAG = "abet"

# SETUP
API_BASE_URL = f"https://{CANVAS_DOMAIN}/api/v1/"
TEMP_DIR = "temp_assignment_files"


def extract_text_from_pdf(file_path: str) -> str:
    """Extracts text content from a PDF file."""
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "".join(page.extract_text() for page in reader.pages)
    except Exception as e:
        return f"[Error extracting text from PDF: {e}]"


def extract_text_from_docx(file_path: str) -> str:
    """Extracts text content from a DOCX file."""
    try:
        doc = docx.Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs)
    except Exception as e:
        return f"[Error extracting text from DOCX: {e}]"


def get_semester_short_code(term_name: str) -> str:
    """Converts 'Fall 2025' to 'f25'."""
    if not term_name:
        return "term"
    match = re.search(r"(\w+)\s+(\d{4})", term_name)
    if match:
        season = match.group(1)[0].lower()
        year = match.group(2)[-2:]
        return f"{season}{year}"
    return "term"


def generate_filename(course_code, semester, assignment_name, label, extension):
    """Generates format: cse100-f20-assignment_name-high.pdf"""
    clean_course = sanitize_filename(course_code).replace("_", "")
    clean_assign = sanitize_filename(assignment_name)
    return f"{clean_course}-{semester}-{clean_assign}-{label}{extension}"


def get_headers(canvas_token: str):
    return {"Authorization": f"Bearer {canvas_token}"}


def sanitize_filename(name: str) -> str:
    """Replaces characters that are invalid in Windows/Linux filenames with an underscore."""
    name = name.replace(" ", "_")
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def api_request(
    url, canvas_token: str, method="GET", params=None, data=None, stream=False
):
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
    headers = get_headers(canvas_token)

    if not url.startswith("https://"):
        url = urljoin(API_BASE_URL, url)
    try:
        time.sleep(0.2)  # To avoid hitting rate limits
        response = requests.request(
            method, url, headers=headers, params=params, data=data, stream=stream
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


def get_paginated_list(endpoint, canvas_token: str, params=None):
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
            response = requests.get(
                url, headers=get_headers(canvas_token), params=params
            )
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
            print(f"API Error: {e}")
            break

    return all_items


def extract_and_save_syllabus(course_id, course_info, canvas_token):
    """Saves syllabus body as HTML, converts it to PDF, and downloads linked PDFs."""
    print("Extracting Syllabus...")
    folder_path = os.path.join(TEMP_DIR, "_Syllabus")
    os.makedirs(folder_path, exist_ok=True)

    body = course_info.get("syllabus_body", "")
    if not body:
        return folder_path

    # 1. Save Raw HTML Body
    html_path = os.path.join(folder_path, "syllabus_body.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(body)

    # 2. Convert HTML to PDF
    # We wrap the body in basic html tags to ensure the renderer handles it correctly
    pdf_path = os.path.join(folder_path, "syllabus_body.pdf")
    try:
        with open(pdf_path, "wb") as pdf_file:
            # Allow blank images to fail gracefully without stopping the script
            pisa.CreatePDF(f"<html><body>{body}</body></html>", dest=pdf_file)
        print(f"  - Rendered syllabus HTML to PDF: syllabus_body.pdf")
    except Exception as e:
        print(f"  - Failed to render syllabus PDF: {e}")

    # 3. Download linked PDF if it exists in the body
    # Regex to find file links: /files/12345
    file_ids = re.findall(r"/files/(\d+)", body)
    for fid in file_ids:
        f_info = api_request(f"files/{fid}", canvas_token)

        if f_info and f_info.get("filename", "").lower().endswith(".pdf"):
            # Save as syllabus.pdf (or keep original name)
            local_path = os.path.join(folder_path, f"syllabus_{f_info['filename']}")
            download_file(f_info["url"], local_path, canvas_token)
            print(f"  - Downloaded linked syllabus PDF: {f_info['filename']}")

    return folder_path


def get_all_assignments(course_id: str, canvas_token: str):
    """Fetches all assignments for a given course."""
    print(f"Fetching all assignments for course {course_id}...")
    endpoint = f"courses/{course_id}/assignments"
    return get_paginated_list(endpoint, canvas_token, params={"include[]": "rubric"})


def find_abet_assignments(all_assignments: list):
    """
    Finds all ABET-related assignments in a course by searching names and rubrics.

    Args:
        course_id (str): The ID of the Canvas course to search within.

    Returns:
        list: A list of assignment objects that match the ABET criteria.
    """
    print("Filtering for ABET assignments...")
    return [
        a
        for a in all_assignments
        if ABET_TAG in a.get("name", "").lower()
        or any(
            ABET_TAG in r.get("description", "").lower() for r in a.get("rubric", [])
        )
    ]


def extract_rubric_assessment_data(submission):
    """Extracts and anonymizes rubric assessment data from a submission."""
    rubric_data = submission.get("rubric_assessment", {})
    if not rubric_data:
        return None
    return {
        cid: {"points": data.get("points"), "comments": data.get("comments", "")}
        for cid, data in rubric_data.items()
    }


def find_abet_outcomes(all_assignments: list[dict]) -> tuple[defaultdict, dict]:
    """Scans assignments, groups them by ABET outcome, and extracts outcome details."""
    outcome_map = defaultdict(list)
    outcome_details = (
        {}
    )  # Store title, description, and long_description for each outcome
    for assign in all_assignments:
        if not (rubric := assign.get("rubric")):
            continue
        for criterion in rubric:
            # We check the main 'description' for the ABET tag
            if "abet" in criterion.get("description", "").lower() and (
                oid := criterion.get("outcome_id")
            ):
                outcome_map[oid].append(assign)
                if oid not in outcome_details:
                    # Use 'description' for the title and main outcome text
                    title_description = criterion.get("description", "").strip()
                    long_description = criterion.get("long_description", "").strip()
                    clean_title = re.sub(r"<[^>]+>", "", title_description).strip()

                    outcome_details[oid] = {
                        "title": clean_title,
                        "full_description": title_description,
                        "long_description": long_description,
                    }
    return outcome_map, outcome_details


def get_representative_submissions(course_id, assignment_id, canvas_token: str):
    """
    Fetches submissions and identifies High, Average, and Low graded artifacts.
    """
    endpoint = f"courses/{course_id}/assignments/{assignment_id}/submissions"

    submissions = get_paginated_list(
        endpoint, canvas_token, params={"include[]": "user"}
    )

    if not submissions:
        return None, None, None

    # Filter for graded submissions only
    graded = sorted(
        [
            s
            for s in submissions
            if s.get("workflow_state") == "graded" and s.get("score") is not None
        ],
        key=lambda s: s["score"],
    )

    if not graded:
        return None, None, None

    # 1. High and Low are easy (sorted list)
    low_sub = graded[0]
    high_sub = graded[-1]

    # 2. Calculate Average
    scores = [s["score"] for s in graded]
    avg_score = sum(scores) / len(scores)

    # 3. Find submission closest to the statistical average
    avg_sub = min(graded, key=lambda s: abs(s["score"] - avg_score))

    return high_sub, avg_sub, low_sub


def download_file(url, local_path, canvas_token: str):
    """
    Downloads a file from a URL to a local path using a streamed response.
    Ensures the connection is closed and handles potential API or file system errors.

    Args:
        url (str): The URL of the file to download.
        local_path (str): The local path where the file will be saved.
        canvas_token (str): The Canvas API access token.

    Returns:
        bool: True if the download was successful, False otherwise.
    """
    try:
        # Get the streamed response object from the API request function
        response = api_request(url, canvas_token, stream=True)

        # api_request returns None on request failure, so we must check for that.
        if response is None:
            print(
                f"  - Download failed for {local_path}: API request did not return a response."
            )
            return False

        # Use the response object as a context manager to ensure the connection is closed.
        with response, open(local_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)

        return True
    except Exception as e:
        # This will catch any exceptions during the request or file I/O operations.
        print(f"  - An error occurred while downloading to {local_path}: {e}")
        return False


def extract_and_save_artifacts(
    assignment, canvas_token: str, course_code: str, semester_code: str
):
    """
    Saves all relevant artifacts for an assignment to a local temporary directory.
    This includes the description, rubric, any documents attached in the description,
    and files from the highest and lowest graded student submissions.

    Args:
        assignment (dict): The assignment object.

    Returns:
        list: A list of local file paths for all successfully saved artifacts.
    """
    sanitized_name = sanitize_filename(assignment["name"])
    assignment_name = f"{assignment['id']}_{sanitized_name}"
    local_path = os.path.join(TEMP_DIR, assignment_name)
    os.makedirs(local_path, exist_ok=True)

    saved_files = []
    extracted_texts = {}

    if description := assignment.get("description"):
        path = os.path.join(local_path, "description.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(description)
        saved_files.append(path)

        for file_id in set(re.findall(r"/files/(\d+)", description)):
            if file_info := api_request(f"files/{file_id}", canvas_token):
                file_local_path = os.path.join(local_path, file_info["filename"])
                if download_file(file_info["url"], file_local_path, canvas_token):
                    saved_files.append(file_local_path)
                    # After downloading, check extension and extract text
                    if file_local_path.lower().endswith(".pdf"):
                        extracted_texts[file_info["filename"]] = extract_text_from_pdf(
                            file_local_path
                        )
                    elif file_local_path.lower().endswith(".docx"):
                        extracted_texts[file_info["filename"]] = extract_text_from_docx(
                            file_local_path
                        )

    if rubric := assignment.get("rubric"):
        path = os.path.join(local_path, "rubric.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rubric, f, indent=4)
        saved_files.append(path)

    high, avg, low = get_representative_submissions(
        assignment["course_id"], assignment["id"], canvas_token
    )

    # List of tuples to iterate cleanly
    representatives = [(high, "high"), (avg, "avg"), (low, "low")]

    for sub, label in representatives:
        if not (sub and sub.get("attachments")):
            continue

        attachment = sub["attachments"][0]
        ext = os.path.splitext(attachment.get("filename", ""))[1]

        # GENERATE NEW FILENAME: cse100-f20-lab1-high.pdf
        new_filename = generate_filename(
            course_code, semester_code, assignment["name"], label, ext
        )

        file_save_path = os.path.join(local_path, new_filename)

        if download_file(attachment["url"], file_save_path, canvas_token):
            saved_files.append(file_save_path)

        # Save metadata
        metadata_path = os.path.join(local_path, f"{label}_details.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "score": sub.get("score"),
                    "points_possible": assignment.get("points_possible"),
                    "original_filename": attachment.get("filename"),
                    "user_id": sub.get("user", {}).get(
                        "id"
                    ),  # This will now populate correctly
                    "rubric_assessment": extract_rubric_assessment_data(sub),
                },
                f,
                indent=2,
            )

        saved_files.append(metadata_path)

    return saved_files, extracted_texts


def upload_files_to_canvas(course_id, folder_path, file_paths, canvas_token: str):
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
                init_data = {
                    "name": filename,
                    "parent_folder_path": folder_path,
                    "on_duplicate": "overwrite",
                }
                upload_info = api_request(
                    f"courses/{course_id}/files", canvas_token, "POST", data=init_data
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
                    api_request(confirmation["location"], canvas_token, "GET")
                print(f"  - Successfully uploaded {filename}")
                break
            except Exception as e:
                print(
                    f"  - ERROR on attempt {attempt + 1}/{MAX_RETRIES} for {filename}: {e}"
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
                else:
                    print(
                        f"  - All {MAX_RETRIES} attempts failed for {filename}. Giving up."
                    )
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
    submissions = grades_fetcher.fetch_assignment_submissions(
        assignment["course_id"], assignment["id"]
    )
    if not submissions:
        print("  - No submissions found.")
        return None

    report_path = os.path.join(local_path, f"grade_report_{assignment['id']}.csv")
    header = ["user_id", "user_name", "score", "submitted_at", "workflow_state"]

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for sub in submissions:
            user = sub.get("user", {})
            writer.writerow(
                [
                    user.get("id", "N/A"),
                    user.get("name", "N/A"),
                    sub.get("score", ""),
                    sub.get("submitted_at", "N/A"),
                    sub.get("workflow_state", "N/A"),
                ]
            )
    print(f"  - Grade report saved to {report_path}")
    return report_path


def generate_outcome_reports(
    grades_fetcher,
    outcome_map,
    outcome_details,
    course_info,
    semester_code,
    course_id: str,
    canvas_token: str,
    student_major_map: dict,
    assignment_texts_map: dict,
):
    """Generates and uploads a rich JSON summary report for each ABET outcome."""
    print(
        "\nGenerating Rich ABET Outcome JSON Reports with Major Breakdown and File Content"
    )
    local_reports_to_upload = []

    for outcome_id, assignments in outcome_map.items():
        outcome_info = outcome_details.get(outcome_id, {})
        outcome_title = outcome_info.get("title", f"Outcome_ID_{outcome_id}")

        print(
            f"\n[DEBUG] Processing Outcome: '{outcome_title}' (Outcome ID: {outcome_id})"
        )

        all_outcome_submissions = []
        major_buckets = defaultdict(list)
        contributing_assignments_data = []

        for assign in assignments:
            print(
                f"[DEBUG]  -> Gathering data from assignment: '{assign['name']}' (ID: {assign['id']})"
            )

            abet_criterion = next(
                (
                    crit
                    for crit in assign.get("rubric", [])
                    if crit.get("outcome_id") == outcome_id
                ),
                None,
            )
            if not abet_criterion:
                print(
                    "[DEBUG]     - SKIPPED: Assignment has no rubric criterion for this specific outcome."
                )
                continue

            abet_points_possible = abet_criterion.get("points", 1)
            submissions = grades_fetcher.fetch_assignment_submissions(
                course_id, assign["id"]
            )
            print(
                f"[DEBUG]     - Fetched {len(submissions)} submissions. Parsing for rubric assessments..."
            )

            print(f"\n\n{submissions}\n\n")

            for sub in submissions:
                if assessment := sub.get("full_rubric_assessment"):
                    for graded_criterion in assessment.get("data", []):
                        if graded_criterion.get("learning_outcome_id") == outcome_id:
                            sub["_abet_score"] = graded_criterion.get("points", 0)
                            sub["_abet_points_possible"] = abet_points_possible
                            all_outcome_submissions.append(sub)

                            print(
                                f"[DEBUG]       - Found relevant score for Submission ID {sub['id']}. Score: {sub['_abet_score']}/{sub['_abet_points_possible']}"
                            )

                            print(
                                f"[DEBUG]         - Attempting to match student to major using login ID..."
                            )
                            print(f"{sub}")
                            print("\n\n")
                            print(f"[DEBUG]         -> User data: {sub.get('user')}")
                            if user_data := sub.get("user"):
                                if login_id := user_data.get("login_id"):
                                    if major := student_major_map.get(login_id):
                                        major_buckets[major].append(sub)
                                        print(
                                            f"[DEBUG]         -> Matched to Major '{major}' via login ID '{login_id}'."
                                        )
                            break  # Move to the next submission

            assignment_info = assign.copy()
            assignment_info["description_files_content"] = assignment_texts_map.get(
                assign["id"], {}
            )
            contributing_assignments_data.append(assignment_info)

        print(
            f"[DEBUG]  -> Data gathering complete. Total relevant submissions: {len(all_outcome_submissions)}. Total students matched to a major: {sum(len(subs) for subs in major_buckets.values())}"
        )

        if not all_outcome_submissions:
            print(
                f"  - WARNING: Skipping report for '{outcome_title}'. No relevant rubric-graded submissions found."
            )
            continue

        major_specific_results = {}
        for major, subs in major_buckets.items():
            num_competent = sum(
                1
                for s in subs
                if (s["_abet_score"] / s["_abet_points_possible"]) >= 0.7
            )
            total_graded = len(subs)
            percent_competent = (
                (num_competent / total_graded) * 100 if total_graded else 0
            )
            major_specific_results[major] = {
                "sample_size": total_graded,
                "number_competent": num_competent,
                "percent_competent": round(percent_competent, 2),
                "outcome_met": percent_competent >= 70.0,
            }

        overall_num_competent = sum(
            1
            for s in all_outcome_submissions
            if (s["_abet_score"] / s["_abet_points_possible"]) >= 0.7
        )
        overall_total_graded = len(all_outcome_submissions)
        overall_percent_competent = (
            (overall_num_competent / overall_total_graded) * 100
            if overall_total_graded
            else 0
        )

        clean_assignments = [
            {
                "id": assign.get("id"),
                "name": assign.get("name"),
                "description": assign.get("description"),
                "description_files_content": assign.get(
                    "description_files_content", {}
                ),
            }
            for assign in contributing_assignments_data
        ]

        # Now, process the collected submissions for major breakdown
        for sub in all_outcome_submissions:
            if user_data := sub.get("user"):
                if login_id := user_data.get("login_id"):
                    if major := student_major_map.get(login_id):
                        major_buckets[major].append(sub)
                        print(
                            f"[DEBUG]  -> Matched Submission ID {sub['id']} to Major '{major}' via SIS ID '{login_id}'."
                        )

        major_specific_results = {}
        for major, subs in major_buckets.items():
            num_competent = sum(
                1
                for s in subs
                if (s["_abet_score"] / s["_abet_points_possible"]) >= 0.7
            )
            total_graded = len(subs)
            percent_competent = (
                (num_competent / total_graded) * 100 if total_graded else 0
            )
            major_specific_results[major] = {
                "sample_size": total_graded,
                "number_competent": num_competent,
                "percent_competent": round(percent_competent, 2),
                "outcome_met": percent_competent >= 70.0,
            }

        overall_num_competent = sum(
            1
            for s in all_outcome_submissions
            if (s["_abet_score"] / s["_abet_points_possible"]) >= 0.7
        )
        overall_total_graded = len(all_outcome_submissions)
        overall_percent_competent = (
            (overall_num_competent / overall_total_graded) * 100
            if overall_total_graded
            else 0
        )

        # 1. Create a clean list of contributing assignments for the report
        clean_assignments = [
            {
                "id": assign.get("id"),
                "name": assign.get("name"),
                "description": assign.get("description"),
                "description_files_content": assign.get(
                    "description_files_content", {}
                ),
            }
            for assign in contributing_assignments_data
        ]

        # 2. Assemble the final, structured report object
        report_data = {
            # Corresponds to requirement 1.a and 1.d (Identification and Description)
            "outcome_identification": {
                "title": outcome_title,
                "description": outcome_info.get("full_description", ""),
                "long_description": outcome_info.get("long_description", ""),
            },
            # Corresponds to requirement 1.c (Class number)
            "course_identification": course_info,
            # Corresponds to requirement 1.e (Results)
            "results": {
                "overall_summary": {
                    "sample_size": overall_total_graded,
                    "number_competent": overall_num_competent,
                    "percent_competent": round(overall_percent_competent, 2),
                    "outcome_met": overall_percent_competent >= 70.0,
                },
                "distribution_by_major": major_specific_results,
            },
            # Corresponds to "Actual instrument used"
            "contributing_assignments": clean_assignments,
        }

        # 3. Write the JSON file to disk
        match = re.search(r"(CS|CSE)\s*ABET\s*\d+", outcome_title, re.IGNORECASE)
        clean_name = (
            match.group(0).replace(" ", "_")
            if match
            else sanitize_filename(outcome_title)
        )
        report_filename = f"OUTCOME_{clean_name}.json"
        report_path = os.path.join(TEMP_DIR, report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)
        local_reports_to_upload.append(report_path)

    if local_reports_to_upload:
        canvas_folder = f"{semester_code}/_ABET_Outcome_Reports"
        upload_files_to_canvas(
            course_id, canvas_folder, local_reports_to_upload, canvas_token
        )


# Fast api endpoint
@app.post("/process-course-with-roster/{course_id}")
async def process_course_with_roster(
    course_id: str,
    canvas_access_token: Annotated[str, Header()],
    roster_file: Optional[UploadFile] = File(None),
    tasks: str = Query("all", description="Tasks to run: 'extract', 'abet', or 'all'"),
):
    # Only run roster parsing if the task actually requires it (ABET or ALL)
    if "abet" in tasks or "all" in tasks:
        if not roster_file:
            raise HTTPException(
                status_code=400,
                detail="The 'roster_file' is required when tasks include 'abet' or 'all'.",
            )
        # Also check for empty value

        try:
            contents = await roster_file.read()
            text_stream = io.TextIOWrapper(io.BytesIO(contents), encoding="utf-8-sig")
            student_major_map = parse_roster_for_major_map(text_stream)
            print(
                f"Successfully parsed roster. Found {len(student_major_map)} CS/CSE students."
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing CSV file: {e}")

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    grades_fetcher = CanvasGradesFetcher(access_token=canvas_access_token)
    course_info = api_request(
        f"courses/{course_id}",
        canvas_access_token,
        params={"include[]": ["syllabus_body", "term"]},
    )
    if not course_info:
        raise HTTPException(
            status_code=404, detail="Course not found or invalid token."
        )

    course_code = course_info.get("course_code", "course")  # e.g., CSE100
    semester_code = get_semester_short_code(
        course_info.get("term", {}).get("name", "")
    )  # e.g., f25

    full_semester_name = f"{semester_code}_{sanitize_filename(course_code)}"

    all_assignments = get_all_assignments(course_id, canvas_access_token)
    if not all_assignments:
        return {"message": "No assignments found in the course."}

    if "extract" in tasks or "all" in tasks:
        syllabus_path = extract_and_save_syllabus(
            course_id, course_info, canvas_access_token
        )
        if syllabus_path:
            # Upload all files found in the syllabus folder
            syllabus_files = [
                os.path.join(syllabus_path, f) for f in os.listdir(syllabus_path)
            ]
            upload_files_to_canvas(
                course_id,
                f"{full_semester_name}/Syllabus",
                syllabus_files,
                canvas_access_token,
            )

    # --- Data Gathering Phase (Always Runs) ---
    # This part is essential for both tasks, so we always run it.
    assignment_texts_map = {}
    print("\n--- Starting Data Gathering Phase ---")
    for assignment in all_assignments:
        print(f"\nGathering artifacts for: {assignment['name']}")
        local_files, extracted_texts = extract_and_save_artifacts(
            assignment, canvas_access_token, course_code, semester_code
        )
        assignment_texts_map[assignment["id"]] = extracted_texts

        # We still generate the grade report locally as it's part of the artifact set
        sanitized_name = sanitize_filename(assignment["name"])
        assignment_folder_path = os.path.join(
            TEMP_DIR, f"{assignment['id']}_{sanitized_name}"
        )
        report_path = generate_assignment_grade_report(
            grades_fetcher, assignment, assignment_folder_path
        )
        if report_path:
            local_files.append(report_path)

        # Only upload the "all_assignments" folder if 'extract' or 'all' is specified
        if "extract" in tasks or "all" in tasks:
            if local_files:
                print(f"  -> Uploading artifacts for '{assignment['name']}'...")
                canvas_folder = f"{full_semester_name}/Assignments/{sanitized_name}"
                upload_files_to_canvas(
                    course_id, canvas_folder, local_files, canvas_access_token
                )
            else:
                print("  -> No artifacts found to upload for this assignment.")

    print("\n--- Data Gathering Complete ---")

    # --- ABET Report Generation Phase (Conditional) ---
    # Only run the ABET report generation if 'abet' or 'all' is specified
    if "abet" in tasks or "all" in tasks:
        print("\n--- Starting ABET Report Generation Phase ---")
        if abet_assignments := find_abet_assignments(all_assignments):
            outcome_map, outcome_details = find_abet_outcomes(abet_assignments)
            if outcome_map:
                generate_outcome_reports(
                    grades_fetcher,
                    outcome_map,
                    outcome_details,
                    course_info,
                    full_semester_name,
                    course_id,
                    canvas_access_token,
                    student_major_map,
                    assignment_texts_map,
                )
            else:
                print(
                    "No assignments with rubric outcomes found for summary report generation."
                )
        else:
            print("No ABET-tagged assignments found.")

    shutil.rmtree(TEMP_DIR)
    return {"message": f"Processing complete for tasks: '{tasks}'."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


# # Steps Overview:
# # 1. Setup: Clean and create a temporary directory for file storage.
# # 2. Find: Identify all target assignments.
# # 3. Process Loop: For each assignment, extract all artifacts locally.
# # 4. Upload: Push the collected local files to a structured folder in Canvas.
# # 5. Teardown: Clean up the temporary directory.
# def main():
#     """Main process to find, extract, and store ABET assignment data."""
#     if os.path.exists(TEMP_DIR):
#         shutil.rmtree(TEMP_DIR)
#     os.makedirs(TEMP_DIR)

#     grades_fetcher = CanvasGradesFetcher()

#     course_info = api_request(f"courses/{SOURCE_COURSE_ID}", params={"include[]": "syllabus_body"})
#     course_name = course_info.get("name") if course_info.get("name") else course_info.get("course_code", "UnknownCourse").replace(" ", "_")
#     semester_year_code = f"Fall_2025_{course_name}"

#     print("\nProcessing: Generating Course-Wide Grade Reports")
#     grade_report_files = grades_fetcher.generate_grade_reports(int(SOURCE_COURSE_ID), TEMP_DIR)
#     if grade_report_files:
#         grades_canvas_folder = f"{semester_year_code}/_Course_Grade_Reports"
#         upload_files_to_canvas(DESTINATION_COURSE_ID, grades_canvas_folder, list(grade_report_files))
#     else:
#         print("Could not generate course-wide grade reports.")

#     abet_assignments = find_abet_assignments(SOURCE_COURSE_ID)
#     if not abet_assignments:
#         print("No ABET-tagged assignments found.")
#         return

#     print(f"\nFound {len(abet_assignments)} ABET assignments to process.")
#     for assignment in abet_assignments:
#         print(f"\nProcessing: {assignment['name']} ")

#         local_files = extract_and_save_artifacts(assignment)
#         assignment_folder_path = os.path.join(TEMP_DIR, f"{assignment['id']}_{assignment['name'].replace(' ', '_')}")
#         assignment_report_path = generate_assignment_grade_report(grades_fetcher, assignment, assignment_folder_path)

#         if assignment_report_path:
#             local_files.append(assignment_report_path)

#         if local_files:
#             canvas_folder = (
#                 f"{semester_year_code}/{assignment['name'].replace(' ', '_')}"
#             )
#             upload_files_to_canvas(DESTINATION_COURSE_ID, canvas_folder, local_files)
#         else:
#             print("No artifacts found to upload for this assignment.")

#     # Outcome folders
#     outcome_map, outcome_details = find_abet_outcomes(abet_assignments)
#     if outcome_map:
#         generate_outcome_reports(grades_fetcher, outcome_map, outcome_details, course_info, semester_year_code)
#     else:
#         print("\nNo assignments with rubric outcomes found for summary report generation.")

#     shutil.rmtree(TEMP_DIR)
#     print("\nProcess finished.")


# if __name__ == "__main__":
#     main()
