#!/usr/bin/env python3
"""
Test script for the Canvas Grades Fetcher
This script tests the grades fetching functionality with minimal data.
"""

import os
import sys
from fetch_grades import CanvasGradesFetcher

def test_basic_functionality():
    """Test basic functionality of the grades fetcher."""
    print("Testing Canvas Grades Fetcher...")
    
    try:
        # Check if access token is set
        if not os.environ.get('canvas_access_token'):
            print("❌ Error: Canvas access token not set.")
            print("Please run: export canvas_access_token='your_token_here'")
            return False
        
        # Initialize fetcher
        print("✅ Initializing Canvas Grades Fetcher...")
        fetcher = CanvasGradesFetcher()
        
        # Test course ID from existing data
        course_id = 240102
        print(f"✅ Testing with course ID: {course_id}")
        
        # Test fetching assignments (lightweight test)
        print("✅ Fetching assignments...")
        assignments = fetcher.fetch_course_assignments(course_id)
        print(f"✅ Found {len(assignments)} assignments")
        
        # Test fetching students (lightweight test)
        print("✅ Fetching students...")
        students = fetcher.fetch_course_students(course_id)
        print(f"✅ Found {len(students)} students")
        
        # Test fetching submissions for first assignment (if any)
        if assignments:
            first_assignment = assignments[0]
            assignment_id = first_assignment['id']
            assignment_name = first_assignment['name']
            
            print(f"✅ Testing submissions fetch for: {assignment_name}")
            submissions = fetcher.fetch_assignment_submissions(course_id, assignment_id)
            print(f"✅ Found {len(submissions)} submissions")
        
        print("\n🎉 All basic tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_full_grades_fetch():
    """Test the full grades fetching functionality."""
    print("\n" + "="*50)
    print("Testing Full Grades Fetch...")
    print("="*50)
    
    try:
        fetcher = CanvasGradesFetcher()
        course_id = 240102
        
        print("Fetching comprehensive grade data...")
        grades_data = fetcher.fetch_course_grades(course_id)
        
        # Save test data
        json_file = fetcher.save_grades_to_json(grades_data, "test_grades_data.json")
        csv_file = fetcher.save_grades_to_csv(grades_data, "test_grades_summary.csv")
        
        # Print summary
        fetcher.print_grades_summary(grades_data)
        
        print(f"\n✅ Test data saved to:")
        print(f"  JSON: {json_file}")
        print(f"  CSV:  {csv_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Full test failed: {e}")
        return False

def main():
    """Main test function."""
    print("Canvas Grades Fetcher - Test Suite")
    print("=" * 50)
    
    # Run basic tests
    basic_success = test_basic_functionality()
    
    if not basic_success:
        print("\n❌ Basic tests failed. Please check your setup.")
        return 1
    
    # Ask user if they want to run full test
    print("\n" + "="*50)
    response = input("Basic tests passed! Run full grades fetch test? (y/n): ").lower().strip()
    
    if response in ['y', 'yes']:
        full_success = test_full_grades_fetch()
        if full_success:
            print("\n🎉 All tests completed successfully!")
            return 0
        else:
            print("\n❌ Full test failed.")
            return 1
    else:
        print("\n✅ Basic tests completed successfully!")
        print("Run 'python fetch_grades.py' for full grades fetch.")
        return 0

if __name__ == "__main__":
    exit(main())
