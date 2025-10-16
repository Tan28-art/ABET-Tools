import requests
import json
import os

canvas_domain = 'https://canvas.asu.edu'

# Get the access token
# to set access token use: export canvas_access_token="your canvas access token" in terminal
access_token = os.environ['canvas_access_token']

url = canvas_domain + '/api/v1/courses'
headers = {'Authorization': 'Bearer ' + access_token}

# all_courses = []
# while url:
#     try:
#         response = requests.get(url, headers=headers)
#         # course_data = response.json()
#         # for course in course_data:
#         #     course_id = course['id']
#         #     course_name = course['name']
#         #     print(f"Course ID: {course_id}, Course Name: {course_name}")
#         all_courses.extend(response.json())
        
#         url = None
#         if 'Link' in response.headers:
#             links = response.headers['Link'].split(',')
#             for link in links:
#                 if 'rel="next"' in link:
#                     # find url for next page
#                     url = link.split(';')[0].strip('<>')
#                     break
            
#     except requests.exceptions.RequestException as e:
#         print(f"Error: {e}")
    
# Testing ground canvas shell has course id: 240102
url = canvas_domain + f'/api/v1/courses/{240102}/assignments'
response = requests.get(url, headers=headers)
assignments = response.json()

# save assignment json'
with open('assignments_structure.json', 'w') as f:
    json.dump(assignments, f)