#!/usr/bin/env python3
"""
Canvas Grades Fetcher
Fetches grades and submission data from Canvas LMS for ABET assessment purposes.
"""

import requests
import json
import os
import csv
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('grades_fetch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CanvasGradesFetcher:
    """Fetches grades and submission data from Canvas LMS."""
    
    def __init__(self, canvas_domain: str = 'https://canvas.asu.edu'):
        """Initialize the Canvas grades fetcher.
        
        Args:
            canvas_domain: Canvas instance domain URL
        """
        self.canvas_domain = canvas_domain
        self.access_token = self._get_access_token()
        self.headers = {'Authorization': f'Bearer {self.access_token}'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _get_access_token(self) -> str:
        """Get Canvas access token from environment variable."""
        token = os.environ.get('canvas_access_token')
        if not token:
            raise ValueError(
                "Canvas access token not found. Please set the 'canvas_access_token' "
                "environment variable. Run: export canvas_access_token='your_token_here'"
            )
        return token
    
    def fetch_course_assignments(self, course_id: int) -> List[Dict[str, Any]]:
        """Fetch all assignments for a given course.
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of assignment dictionaries
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/assignments"
        logger.info(f"Fetching assignments for course {course_id}")
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            assignments = response.json()
            logger.info(f"Successfully fetched {len(assignments)} assignments")
            return assignments
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching assignments: {e}")
            raise
    
    def fetch_assignment_submissions(self, course_id: int, assignment_id: int) -> List[Dict[str, Any]]:
        """Fetch all submissions for a specific assignment.
        
        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID
            
        Returns:
            List of submission dictionaries
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
        params = {
            'include': ['user', 'submission_comments', 'submission_history'],
            'per_page': 100
        }
        
        logger.info(f"Fetching submissions for assignment {assignment_id}")
        
        all_submissions = []
        while url:
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                submissions = response.json()
                all_submissions.extend(submissions)
                
                # Handle pagination
                url = None
                if 'Link' in response.headers:
                    links = response.headers['Link'].split(',')
                    for link in links:
                        if 'rel="next"' in link:
                            url = link.split(';')[0].strip('<>')
                            break
                            
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching submissions for assignment {assignment_id}: {e}")
                break
        
        logger.info(f"Successfully fetched {len(all_submissions)} submissions")
        return all_submissions
    
    def fetch_course_students(self, course_id: int) -> List[Dict[str, Any]]:
        """Fetch all students enrolled in a course.
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of student dictionaries
        """
        url = f"{self.canvas_domain}/api/v1/courses/{course_id}/users"
        params = {
            'enrollment_type': 'student',
            'per_page': 100
        }
        
        logger.info(f"Fetching students for course {course_id}")
        
        all_students = []
        while url:
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                students = response.json()
                all_students.extend(students)
                
                # Handle pagination
                url = None
                if 'Link' in response.headers:
                    links = response.headers['Link'].split(',')
                    for link in links:
                        if 'rel="next"' in link:
                            url = link.split(';')[0].strip('<>')
                            break
                            
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching students: {e}")
                break
        
        logger.info(f"Successfully fetched {len(all_students)} students")
        return all_students
    
    def fetch_course_grades(self, course_id: int) -> Dict[str, Any]:
        """Fetch complete grade data for a course including assignments, submissions, and students.
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            Dictionary containing course grade data
        """
        logger.info(f"Starting comprehensive grade fetch for course {course_id}")
        
        # Fetch course data
        course_data = {
            'course_id': course_id,
            'fetch_timestamp': datetime.now().isoformat(),
            'assignments': [],
            'students': [],
            'grades_summary': {}
        }
        
        try:
            # Fetch assignments
            assignments = self.fetch_course_assignments(course_id)
            course_data['assignments'] = assignments
            
            # Fetch students
            students = self.fetch_course_students(course_id)
            course_data['students'] = students
            
            # Fetch submissions for each assignment
            for assignment in assignments:
                assignment_id = assignment['id']
                assignment_name = assignment['name']
                
                logger.info(f"Fetching submissions for assignment: {assignment_name}")
                submissions = self.fetch_assignment_submissions(course_id, assignment_id)
                
                # Add submissions to assignment data
                assignment['submissions'] = submissions
                
                # Calculate grade statistics
                graded_submissions = [s for s in submissions if s.get('grade') is not None]
                if graded_submissions:
                    grades = [float(s['grade']) for s in graded_submissions if s['grade']]
                    course_data['grades_summary'][assignment_name] = {
                        'total_submissions': len(submissions),
                        'graded_submissions': len(graded_submissions),
                        'average_grade': sum(grades) / len(grades) if grades else 0,
                        'max_grade': max(grades) if grades else 0,
                        'min_grade': min(grades) if grades else 0,
                        'points_possible': assignment.get('points_possible', 0)
                    }
            
            logger.info("Successfully completed comprehensive grade fetch")
            return course_data
            
        except Exception as e:
            logger.error(f"Error in comprehensive grade fetch: {e}")
            raise
    
    def save_grades_to_json(self, grades_data: Dict[str, Any], filename: str = None) -> str:
        """Save grades data to JSON file.
        
        Args:
            grades_data: Grades data dictionary
            filename: Output filename (optional)
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"grades_data_{grades_data['course_id']}_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(grades_data, f, indent=2)
        
        logger.info(f"Grades data saved to {filename}")
        return filename
    
    def save_grades_to_csv(self, grades_data: Dict[str, Any], filename: str = None) -> str:
        """Save grades data to CSV file for easy analysis.
        
        Args:
            grades_data: Grades data dictionary
            filename: Output filename (optional)
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"grades_summary_{grades_data['course_id']}_{timestamp}.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow(['Assignment Name', 'Total Submissions', 'Graded Submissions', 
                           'Average Grade', 'Max Grade', 'Min Grade', 'Points Possible'])
            
            # Write grade summary data
            for assignment_name, summary in grades_data['grades_summary'].items():
                writer.writerow([
                    assignment_name,
                    summary['total_submissions'],
                    summary['graded_submissions'],
                    round(summary['average_grade'], 2),
                    summary['max_grade'],
                    summary['min_grade'],
                    summary['points_possible']
                ])
        
        logger.info(f"Grades summary saved to {filename}")
        return filename
    
    def print_grades_summary(self, grades_data: Dict[str, Any]) -> None:
        """Print a formatted summary of grades to console.
        
        Args:
            grades_data: Grades data dictionary
        """
        print(f"\n{'='*60}")
        print(f"GRADES SUMMARY - Course ID: {grades_data['course_id']}")
        print(f"Fetched: {grades_data['fetch_timestamp']}")
        print(f"{'='*60}")
        
        print(f"\nTotal Assignments: {len(grades_data['assignments'])}")
        print(f"Total Students: {len(grades_data['students'])}")
        
        print(f"\n{'Assignment Name':<40} {'Avg Grade':<10} {'Graded/Total':<12} {'Points':<8}")
        print("-" * 70)
        
        for assignment_name, summary in grades_data['grades_summary'].items():
            avg_grade = summary['average_grade']
            graded = summary['graded_submissions']
            total = summary['total_submissions']
            points = summary['points_possible']
            
            print(f"{assignment_name[:39]:<40} {avg_grade:<10.2f} {graded}/{total:<10} {points:<8}")


def main():
    """Main function to demonstrate grades fetching."""
    try:
        # Initialize fetcher
        fetcher = CanvasGradesFetcher()
        
        # Course ID from the existing test data
        course_id = 240102
        
        print("Canvas Grades Fetcher")
        print("=" * 50)
        print(f"Fetching grades for course: {course_id}")
        print("This may take a few minutes depending on the number of assignments...")
        
        # Fetch comprehensive grade data
        grades_data = fetcher.fetch_course_grades(course_id)
        
        # Save data to files
        json_file = fetcher.save_grades_to_json(grades_data)
        csv_file = fetcher.save_grades_to_csv(grades_data)
        
        # Print summary
        fetcher.print_grades_summary(grades_data)
        
        print(f"\nData saved to:")
        print(f"  JSON: {json_file}")
        print(f"  CSV:  {csv_file}")
        print(f"  Log:  grades_fetch.log")
        
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
