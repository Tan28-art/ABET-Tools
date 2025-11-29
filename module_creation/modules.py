import requests
import json
import os
import re
import shutil
import sys
from urllib.parse import urljoin

# CONFIGURATION
CANVAS_DOMAIN = "canvas.asu.edu"
CANVAS_TOKEN = os.getenv("canvas_access_token")
SOURCE_COURSE_ID = "240102"
DESTINATION_COURSE_ID = "240102" #226368

# SETUP
API_BASE_URL = f"https://{CANVAS_DOMAIN}/api/v1/"
CANVAS_BASE_URL = f"https://{CANVAS_DOMAIN}/"
HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}

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

def find_file_folder(course_id, semester, year):
    """
    Finds all course data file folders for a specific semester-year combination.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        semester (str): The semester to filter file folders by.
        year (str): The year to filter file folders by.

    Returns:
        list: A list of folder objects that match the semester-year combination.
    """
    print(f"Finding all {semester} {year} folders in course {course_id}...")
    endpoint = f"courses/{course_id}/folders"
    file_folders = get_paginated_list(endpoint, params={"include[]":"folders"})

    return[
        f
        for f in file_folders
        if f"{semester}_{year}" in f.get("full_name").lower()
    ]

def find_files(course_id, course, semester, year, file_folders):
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
    print(f"\nSearching for {course} assignment data in course {course_id}...")
    endpoint = f"courses/{course_id}/files"

    folder_to_files = {}
    for f in file_folders: #search for files associated with each folder
        full_folder_name = f.get("full_name")
        abbrv_name = f.get("name")
        if f"{semester.capitalize()}_{year}" in abbrv_name: #sort out main folder name
            continue
        else:
            if course in full_folder_name:
                folder_id = f.get("id")
                print(f"Folder: {full_folder_name} | Id: {folder_id}")
                files = get_paginated_list(endpoint)
                found_files = [f for f in files if f.get("folder_id") == folder_id]
                folder_to_files[abbrv_name] = found_files # map folder_to_file provided folder_name key
    return folder_to_files

def create_page(course_id):
    """
    test_file_url = f"{CANVAS_BASE_URL}courses/{course_id}/files/117953140"

    page_data = {
        "wiki_page": {
            "title": "Test_page",
            "body": f"<h1>Test</h1><p>Page information</p><a href={test_file_url}>File Link</a>"
        }
    }
    """
    try:
        with open('abet_page.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error: {e}")
    page_data = {
        "wiki_page": {
            "title": "Test_page",
            "body": f"{html_content}"
        }
    }

    try:
        upload_response = requests.post(url=f"{API_BASE_URL}courses/{course_id}/pages", json=page_data, headers=HEADERS)
        upload_response.raise_for_status()
        if confirmation := upload_response.json():
            print(f"  - Successfully uploaded page")
    except Exception as e:
        print(f"  - Failed to upload page : {e}")

def main():
    """Main process to find, and store course assignment data in a module."""

    if len(sys.argv) == 3:
        semester = sys.argv[1]   
        year = sys.argv[2]
        print(f"Searching for all course data from {semester} {year}...")
    else:
        print("Usage: python module_creation_api.py <semester> <year>")
        return
    
 #   create_page(DESTINATION_COURSE_ID)


 # find all folders labeled with "semester_year"
    file_folders = find_file_folder(DESTINATION_COURSE_ID, semester, year)
    unique_courses = set()
    if not file_folders:
        print("No file folders found.")
        return
    print(f"\nFound {len(file_folders)} file folders with course data.")
    for folder in file_folders:
        source_course = folder['full_name'].rsplit('/')[1]
        unique_courses.add(source_course.split('_')[2]) # add name after semester_year identifier
        print(f"\nFound: {folder['full_name']}")


    print("\nProcess finished.")

if __name__ == "__main__":
    main()