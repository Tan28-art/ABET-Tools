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
    print(f"Searching for course assignment data in course {course_id}...")
    endpoint = f"courses/{course_id}/folders"
    file_folders = get_paginated_list(endpoint, params={"include[]":"folders"})

    return[
        f
        for f in file_folders
        if f"{semester}_{year}" in f.get("full_name").lower()
    ]

def find_modules(course_id, semester, year):
    """
    Find module labeled with the semester and year to check if it already exists.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        semester (str): The semester to check modules for.
        year (str): The year to check modules for.

    Returns:
        module object: A module object that matches the semester-year combination.
        False if the module does not exist.
    """
    print(f"Searching for course data module {semester.capitalize()} {year} in course {course_id}...")
    endpoint = f"courses/{course_id}/modules"
    modules = get_paginated_list(endpoint)

    for m in modules:
        if f"{semester} {year}" in m.get("name").lower():
            print(f"{m.get("name")} already exists")
            return m
    return False

def find_files(course_id, semester, year, file_folders):
    """
    Finds all course data files for a specific semester-year combination.

    Args:
        course_id (str): The ID of the Canvas course to search within.
        semester (str): The semester to filter file folders by.
        year (str): The year to filter file folders by.

    Returns:
        list: A list of file objects that match the semester-year combination.
    """
    print(f"\nSearching for course assignment data in course {course_id}...")
    endpoint = f"courses/{course_id}/files"

    folder_to_files = {}
    for f in file_folders: #search for files associated with each folder
        folder_name = f.get("name")
        folder_id = f.get("id")
        print(f"Folder: {folder_name} | Id: {folder_id}")
        files = get_paginated_list(endpoint)
        found_files = [f for f in files if f.get("folder_id") == folder_id]
        folder_to_files[folder_name] = found_files # map folder_to_file provided folder_name key
    return folder_to_files

def upload_module_to_canvas(course_id, semester, year):
    """
    Uploads a module for a course's data to Canvas.

    Args:
        course_id (str): The ID of the destination Canvas course.
        semester (str): Semester to label the module by.
        year (str): Year to label the module by.
    """
    module_name = f"{semester.capitalize()} {year} Course Data"
    print(f"Uploading '{module_name}' module to Canvas...")
    try:
        module_data = {
            "module": {
                "name": module_name,
                "position": 1
            }
        }
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules",headers=HEADERS,json=module_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(
            f"API Error on: {e}\nResponse: {e.response.text if e.response else 'N/A'}"
        )
    return find_modules(course_id, semester, year)

def add_single_module_item(course_id, module_id, file_id, file_name, position):
    """
    Adds a single module item to a module

    Args:
        course_id (str): The ID of the destination Canvas course.
        module_id (str): The module_id of the module the file will be added to
        file_id (str): The file_id of the file which will be added.
        file_name (str): The name of the file which will be added.
        position (int): controls grouping of files in the module

    Returns:
        int: updated position for grouping of files in the module
    """
    try:
        module_item_data = {"module_item": {
            "position": position,
            "title": file_name,
            "indent": 1,
            "type": "File",
            "content_id": file_id #single module id
        }}
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules/{module_id}/items",headers=HEADERS,json=module_item_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
        return position + 1 #update position for next module items
    except Exception as e:
        print(f"  - Failed to upload: {e}")
        response.raise_for_status()
        print(f"Status: {response.status_code}")

def add_title_module_item(course_id, module_id, assignment_name, position):
    """
    Adds the subheader for a given assignment_name - to allow for better grouping of assignment data

    Args:
        course_id (str): The ID of the destination Canvas course.
        module_id (str): The module_id of the module the files will be added to
        assignment_name (str): The name of the assignment which all added files are part of.
        position (int): controls grouping of files in the module
    Returns:
        int: updated position for grouping of files in the module
    """
    try:
        module_item_data = {"module_item": {
            "position": position,
            "title": assignment_name,
            "indent": 0,
            "type": "SubHeader",
        }}
        response = requests.post(f"{API_BASE_URL}courses/{course_id}/modules/{module_id}/items",headers=HEADERS,json=module_item_data)
        response.raise_for_status()
        print(f"Status: {response.status_code}")
        return position + 1 #update position for next module items
    except Exception as e:
        print(f"  - Failed to upload: {e}")
        response.raise_for_status()
        print(f"Status: {response.status_code}")

def create_module_items(course_id, file_folder, module_id, position):
    """
    Creates module items for a specific module_id.

    Args:
        course_id (str): The ID of the destination Canvas course.
        file_folder (list): list of the files which will be added (from folder)
        module_id (str): module_id of the module the files will be added to
        position (int): controls grouping of files in the module
    """
    for folder in file_folder:
        name = folder.get("display_name")
        id = folder.get("id")
        print(f"NAME: {name} | ID: {id}")
        position = add_single_module_item(course_id, module_id, id, name, position)

def delete_module(course_id, module_id):
    try: 
        response = requests.delete(f"{API_BASE_URL}courses/{course_id}/modules/{module_id}",headers=HEADERS)
        response.raise_for_status()
        print(f"Module {module_id} was deleted")
        print(f"Status: {response.status_code}")
    except Exception as e:
        print(f"  - Failed to upload: {e}")
        response.raise_for_status()
        print(f"Status: {response.status_code}")

def main():
    """Main process to find, and store course assignment data in a module."""

    course_info = api_request(f"courses/{DESTINATION_COURSE_ID}")
    canvas_folder = f"Fall_2025_{course_info.get('name', 'UnknownCourse')}"

    # find all folders labeled with "fall_2025"
    file_folders = find_file_folder(DESTINATION_COURSE_ID, "fall", "2025")
    if not file_folders:
        print("No file folders found.")
        return
    print(f"\nFound {len(file_folders)} file folders with course data.")
    for folder in file_folders:
        print(f"\nFound: {folder['full_name']}")

    # upload module labeled "fall_2025" only if it is unique
    module_obj = find_modules(DESTINATION_COURSE_ID, "fall", "2025")
    if module_obj == False:
        module_obj = upload_module_to_canvas(DESTINATION_COURSE_ID, "fall", "2025")
    else: # delete current module and reupload it with current data
        old_module_id = (module_obj.get("id"))
        delete_module(DESTINATION_COURSE_ID, old_module_id)
        module_obj = upload_module_to_canvas(DESTINATION_COURSE_ID, "fall", "2025")
    
    # find all files to place in module
    module_id = (module_obj.get("id"))
    files = find_files(DESTINATION_COURSE_ID, "fall", "2025", file_folders)
    for f in files:
        position = 1 # control grouping of files in the module
        print(f"Name: {f}")
        listed_files = files.get(f)
        # add the "subheader" folder name
        position = add_title_module_item(DESTINATION_COURSE_ID, module_id, f, position)
        # add all module items for the given "subheader" folder-name
        create_module_items(DESTINATION_COURSE_ID, listed_files, module_id, position)
    print("\nProcess finished.")

if __name__ == "__main__":
    main()
