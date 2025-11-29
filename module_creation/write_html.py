import requests
import json
import os
import re
import shutil
import sys
from urllib.parse import urljoin
from urllib.parse import unquote

# CONFIGURATION
CANVAS_DOMAIN = "canvas.asu.edu"
CANVAS_TOKEN = os.getenv("canvas_access_token")
SOURCE_COURSE_ID = "240102"
DESTINATION_COURSE_ID = "240102" #226368

# SETUP
API_BASE_URL = f"https://{CANVAS_DOMAIN}/api/v1/"
CANVAS_BASE_URL = f"https://{CANVAS_DOMAIN}/"
HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}


def write_to_page(content):
    try:
        with open('test.html', 'a') as f:
            f.write(content)
    except IOError as e:
        print(f"Error writing to the html file: {e}")


def add_abet_table_row():
    student_outcome_cell = """
<tr>
    <td>CSE(1)<br>an ability to identify, formulate, and solve complex engineering problems by applying principles of engineering, science, and mathematics.</td>
    <td>
                <p>CSE Placeholder Assessment Report and Instrument:</p>
                <ul>
                    <li>CSE Placeholder Assessment Report.pdf</li>
                    <li>CSE Placeholder Homework.pdf</li>
                </ul>
                <p>CSE Placeholder Assessment Report and Instrument:</p>
                <ul>
                    <li>CSE Placeholder Assessment Report.pdf</li>
                    <li>CSE Placeholder Project.pdf</li>
                </ul>
            </td>
    <td>CSE Placeholder:</td>
</tr>
"""
    write_to_page(student_outcome_cell)

def set_up_abet_page():
    content = """
<h1 class="page-title">CSE-ABET Assessment Instruments and Samples</h1>
<h3>Assessment Instruments and Student Samples</h3>
<p>CSE-ABET Assessment Plan and Coverage.pdf</p>

<table style="width: 100%;" border="1">
    <thead>
        <tr>
            <th>Student Outcome</th>
            <th>Assessment Instruments</th>
            <th>Student Work Samples</th>
        </tr>
    </thead>
    <tbody>
"""
    write_to_page(content)
    add_abet_table_row()

    write_to_page("</tbody></table>")

def add_graded_work_course_page(file_folders, files, lab_projects, exams):
    table_set_up = """<h3>Graded Student Work</h3>
<p>Lab Projects</p>
<table style="width: 100%;" border="1">
    <thead>
        <tr>
            <th>Assessment</th>
            <th>High</th>
            <th>Mid</th>
            <th>Low</th>
        </tr>
    </thead>
"""

    write_to_page(table_set_up)
    for lab in lab_projects:
        lab_high = ""
        lab_low = ""
        lab_mid = ""
        lab_link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{lab.get("id")}"

        for folder in file_folders:
            if lab.get("folder_id") == folder.get("id"):
                folders_files = files[folder.get("name")]
                for file in folders_files:
                    filename = file.get("filename").lower()
                    link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{file.get("id")}"
                    if "high.pdf" in filename or "high.txt" in filename:
                        lab_high = f"<a href={link}>{filename}</a>"
                    if "low.pdf" in filename or "low.txt" in filename:
                        lab_low = f"<a href={link}>{filename}</a>"
                    if "avg.pdf" in filename or "avg.txt" in filename:
                        lab_mid = f"<a href={link}>{filename}</a>"
        # set row information:
        row = f"""
        <tbody>
            <tr>
                <td><a href={lab_link}>{unquote(lab.get("filename"))}</a></td>
                <td>{lab_high}</td>
                <td>{lab_mid}</td>
                <td>{lab_low}</td>
            </tr>
        </tbody>
    """
        write_to_page(row) #repeat for however many rows there are
    
    write_to_page("</table>") #close table
    for exam in exams:
        exam_high = ""
        exam_low = ""
        exam_mid = ""
        exam_link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{exam.get("id")}"

        for folder in file_folders:
            if exam.get("folder_id") == folder.get("id"):
                folders_files = files[folder.get("name")]
                for file in folders_files:
                    filename = file.get("filename").lower()
                    link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{file.get("id")}"
                    if "high.pdf" in filename or "high.txt" in filename:
                        exam_high = f"<a href={link}>{filename}</a>"
                    if "low.pdf" in filename or "low.txt" in filename:
                        exam_low = f"<a href={link}>{filename}</a>"
                    if "avg.pdf" in filename or "avg.txt" in filename:
                        exam_mid = f"<a href={link}>{filename}</a>"

    exam_set_up = """
<p>Exams</p>
<table style="width: 100%;" border="1">
    <thead>
        <tr>
            <th>Assessment</th>
            <th>High</th>
            <th>Mid</th>
            <th>Low</th>
        </tr>
    </thead>
"""
    write_to_page(exam_set_up)
    row = f"""
<tbody>
        <tr>
            <td><a href={exam_link}>{unquote(exam.get("filename"))}</a></td>
            <td>{exam_high}</td>
            <td>{exam_mid}</td>
            <td>{exam_low}</td>
        </tr>
    </tbody>
"""
    write_to_page(row) #repeat for however many rows there are
    write_to_page("</table>") #close table

def get_lab_projects(file_folders, files):
    lab_projects = []
    for folder in file_folders:
        if f"assignments" in folder.get("full_name").lower():
            if f"assignment" in folder.get("name").lower():
                folders_files = files[folder.get("name")]
                for file in folders_files:
                    #print(f"{file.get("filename")} | {file.get("id")}")
                    filename = file.get("filename").lower()
                    if f"assignment" in filename:
                        if "avg" not in filename and "high" not in filename and "low" not in filename:
                            lab_projects.append(file)
    return lab_projects

def get_exams(file_folders, files):
    exams = []
    for folder in file_folders:
        if f"assignments" in folder.get("full_name").lower():
            if f"quiz" in folder.get("name").lower() or f"exam" in folder.get("name") or f"test" in folder.get("name"):
                folders_files = files[folder.get("name")]
                for file in folders_files:
                    print(f"{file.get("filename")} | {file.get("id")}")
                    if f"description" in file.get("filename").lower():
                        exams.append(file)
    return exams

def set_up_course_page(file_folders, files, course_code, course_name, semester, year):
    
    # Find the course's syllabus
    for file in files["Syllabus"]:
        if file.get("filename") == 'syllabus_body.pdf':
            syllabus_id = file.get("id")
            print(syllabus_id)
    syllabus_link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{syllabus_id}"
# <h1 class="page-title">{course_code}: {course_name} ({semester.capitalize()} {year})</h1>
    content = f"""

<h3>Syllabus and Course Schedule</h3>
<ul>
    <li><a href={syllabus_link}>{course_code}_syllabus_and_schedule.pdf</a></li><br>
</ul>
<h3>Lab Projects, Quizzes, and Exams</h3>
<ul>
<li>Lab Projects<br>
    <ul>"""
    write_to_page(content)
    # add lab projects:
    lab_projects = get_lab_projects(file_folders, files)
    for file in lab_projects:
        link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{file.get("id")}"
        write_to_page(f"<li><a href={link}>{unquote(file.get("filename"))}</a></li>")
    content = """
    </ul>
</li>
<li>Exams<br>
    <ul>"""
    write_to_page(content)
    # add quizzes/exams
    exams = get_exams(file_folders, files)
    for file in exams:
        link = f"{CANVAS_BASE_URL}courses/{SOURCE_COURSE_ID}/files/{file.get("id")}"
        write_to_page(f"<li><a href={link}>{file.get("filename")}</a></li>")
    content = """
    </ul>
</li>
"""
    write_to_page(content)
    add_graded_work_course_page(file_folders, files, lab_projects, exams)

def add_to_canvas(course_code, course_name, semester, year):
    try:
        with open('test.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error: {e}")
    page_data = {
        "wiki_page": {
            "title": f"{course_code}: {course_name} ({semester.capitalize()} {year})",
            "body": f"{html_content}"
        }
    }

    try:
        upload_response = requests.post(url=f"{API_BASE_URL}courses/{DESTINATION_COURSE_ID}/pages", json=page_data, headers=HEADERS)
        upload_response.raise_for_status()
        if confirmation := upload_response.json():
            print(f"  - Successfully uploaded page")
    except Exception as e:
        print(f"  - Failed to upload page : {e}")
    return upload_response.json()


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

def upload_module_to_canvas(course_id, course_code, semester, year):
    """
    Uploads a module for a course's data to Canvas.

    Args:
        course_id (str): The ID of the destination Canvas course.
        course (str): unique course title string
        semester (str): Semester to label the module by.
        year (str): Year to label the module by.
    """
    module_name = f"Courses - Course Folders and Student Work Samples ({semester.capitalize()} {year})"
    print(f"Uploading '{module_name}' module to Canvas...")
    try:
        module_data = {
            "module": {
                "name": module_name,
                "position": 1,
            }
        }
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules",headers=HEADERS,json=module_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(
            f"API Error on: {e}\nResponse: {e.response.text if e.response else 'N/A'}"
        )
    return response.json()

def add_single_module_item(course_id, module_id, page):
    """
    Adds a single module item to a module

    Args:
        course_id (str): The ID of the destination Canvas course.
        module_id (str): The module_id of the module the file will be added to
        page_id (str): The page_id of the page which will be added.
        page_name (str): The name of the page which will be added.

    Returns:
        int: updated position for grouping of files in the module
    """
    try:
        module_item_data = {"module_item": {
            "title": page.get("title"),
            "type": "Page",
            "page_url": page.get("url"), #single module id
        }}
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules/{module_id}/items",headers=HEADERS,json=module_item_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
    except Exception as e:
        print(f"  - Failed to upload: {e}")
        response.raise_for_status()
        print(f"Status: {response.status_code}")

def find_file_folder(course_id, term, course_code):
    """
    Finds all course data file folders for a specific semester-year combination.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        term (str): The term to filter file folders by.
        course_code (str): The course_code to filter file folders by.

    Returns:
        list: A list of folder objects that match the term-course_code combination.
    """
    print(f"Finding all {term}_{course_code} folders in course {course_id}...")
    endpoint = f"courses/{course_id}/folders"
    file_folders = get_paginated_list(endpoint, params={"include[]":"folders"})

    return[
        f
        for f in file_folders
        if f"{term}_{course_code}" in f.get("full_name")
    ]

def find_unique_courses(file_folders):
    # find all folders labeled with "semester_year"
    unique_courses = set()
    if not file_folders:
        print("No file folders found.")
        return
    print(f"\nFound {len(file_folders)} file folders with course data.")
    for folder in file_folders:
        source_course = folder['full_name'].rsplit('/')[1]
        unique_courses.add(source_course.split('_')[2]) # add name after semester_year identifier
        print(f"\nFound: {folder['full_name']}")
   # add_to_canvas()
    for course in unique_courses:
        print(course)
    return unique_courses

def get_files(course_id, course_code, semester, year, file_folders):
    """
    Finds all course data files for a specific semester-year combination.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        course (str): unique course title string
        semester (str): The semester to filter file folders by.
        year (str): The year to filter file folders by.

    Returns:
        list: A list of file objects that match the course, semester-year combination.
    """
    print(f"\nSearching for {course_code} assignment data in course {course_id}...")
    endpoint = f"courses/{course_id}/files"

    folder_to_files = {}
    for f in file_folders: #search for files associated with each folder
        full_folder_name = f.get("full_name")
        abbrv_name = f.get("name")
        if f"{course_code}" in abbrv_name: #sort out main folder name
            continue
        else:
            if course_code in full_folder_name:
                folder_id = f.get("id")
                print(f"Folder: {full_folder_name} | Id: {folder_id}")
                files = get_paginated_list(endpoint)
                found_files = [f for f in files if f.get("folder_id") == folder_id]
                folder_to_files[abbrv_name] = found_files # map folder_to_file provided folder_name key
    return folder_to_files

def main():
   # add_to_canvas()
    semester = "fall"
    year = "2025"

   # find course_code to sort folders by
    course_info = requests.get(url=f"{API_BASE_URL}courses/{SOURCE_COURSE_ID}", headers=HEADERS).json()
    course_code = course_info.get('course_code')
    course_name = course_info.get('name')
    #print("Course info:", course_info)

    file_folders = find_file_folder(SOURCE_COURSE_ID, "term", course_code)
    files = get_files(SOURCE_COURSE_ID, course_code, "fall", "2025", file_folders)

    """for folder in file_folders:
        if f"all_assignments" in folder.get("full_name").lower():
            #print("folder", folder.get("name"))
            folders_files = files[folder.get("name")]
            for file in folders_files:
                print(f"{file.get("filename")} | {file.get("id")}")
    unique_courses = find_unique_courses(file_folders)
"""
   

    # add course folder module
    module = upload_module_to_canvas(SOURCE_COURSE_ID, course_code, semester, year)

    # set_up_abet_page()
    set_up_course_page(file_folders, files, course_code, course_name, semester, year)
    page = add_to_canvas(course_code, course_name, semester, year)
    add_single_module_item(DESTINATION_COURSE_ID, module.get("id"), page)

if __name__ == "__main__":
    main()