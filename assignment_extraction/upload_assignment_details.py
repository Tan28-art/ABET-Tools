# Script to extract assignment inforamtion and store it in the files section in canvas

import requests
import json
import os
from canvasapi import Canvas

canvas_domain = "canvas.asu.edu"
canvas_api_key = os.getenv("canvas_access_token")


def extract_assignment_details(course, assignment):
    """Extract assignment structure for a single assignment"""
    try:
        target_folder = os.path.join(OUTPUT_DIR, f"{course.name}", f"{assignment.id}_{assignment.name}")
        os.makedirs(target_folder, exist_ok=True)
        
        created_files = []
        
        # save assignment description
        if assignment.description:
            description_file_path = os.path.join(target_folder, f"description.html")
            with open(description_file_path, 'w', encoding='utf-8') as desc_file:
                desc_file.write(assignment.description)
            created_files.append(description_file_path)
        
        # save assignment rubric
        if assignment.rubric:
            rubric_filename = os.path.join(target_folder, "rubric.json")
            with open(rubric_filename, "w", encoding="utf-8") as f:
                json.dump(assignment.rubric, f, indent=4)
            created_files.append(rubric_filename)
        
        return created_files
        
    except Exception as e:
        print(f"Error extracting assignment details: {e}")
        return []
        
        
def get_assignment_details(course, assignment_id):
    """
    Args:
        course (Course): The canvasapi Course object.
        assignment_id (int): The ID of the assignment to fetch.

    Returns:
        Assignment: The canvasapi Assignment object, or None if not found.
    """
    print(f"-> Fetching details for Assignment ID: {assignment_id}...")
    try:
        assignment = course.get_assignment(assignment_id)
        print(f"  - Success. Found Assignment: '{assignment.name}'")
        return assignment
    except Exception as e:
        print(f"Error fetching assignment details: {e}")
        return None
        
def upload_assignment_data_to_canvas(course, assignment):
    """
    Creates a folder in Canvas and uploads the assignment's data using temporary files.
    
    Args:
        course (Course): The canvasapi Course object.
        assignment (Assignment): The canvasapi Assignment object containing the data.
    """
    assignment_name = assignment.name
    canvas_folder_path = f"{course.name}/{assignment.id}_{assignment_name}"
    
    # Create or get the folder in Canvas
    """
    Canvas has a weird API for folders; you have to navigate to the parent folder first.
    """
    # Start with the course as the initial parent object.
    parent_object = course 
    path_parts = canvas_folder_path.split('/')
    
    # Traverse the path one level at a time
    for i, part in enumerate(path_parts):
        if not part: continue
        
        # Determine where to search for the next subfolder
        if i == 0:
            # For the first part, get folders from the course itself
            subfolders = parent_object.get_folders()
        else:
            # For subsequent parts, get folders from the parent FOLDER object
            subfolders = parent_object.get_folders()

        found_next_folder = None
        for subfolder in subfolders:
            if subfolder.name == part:
                found_next_folder = subfolder
                break
        
        if found_next_folder:
            parent_object = found_next_folder
        else:
            parent_object = parent_object.create_folder(part)

    canvas_folder = parent_object

    created_files = extract_assignment_details(course, assignment)
    for file_path in created_files:
        try:
            canvas_folder.upload(file_path)
        except Exception as e:
            print(f"Error uploading file {file_path}: {e}")
    
    return

def main():
    canvas = Canvas(f"https://{canvas_domain}", canvas_api_key)
        
    # get course and assignment objects
    course = canvas.get_course(240102)
    assignment = course.get_assignment(6803004)

    # upload assignment information to canvas
    upload_assignment_data_to_canvas(course, assignment)

if __name__ == "__main__":
    main()
