#!/usr/bin/python3
import csv
import io
import re
from typing import TextIO

# regex to detect CS / CSE majors/plans
CS_CSE_REGEX = re.compile(
    r"""
    (?:\bcomputer\s+science\b)      |   # "Computer Science"
    (?:\bcomputer\s+sci\b)          |   # "Computer Sci"
    (?:\bcomputer\s+systems\s+eng)  |   # "Computer Systems Eng"
    (?:\bcse\b)                         # "CSE"
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_cs_or_cse(plan: str) -> bool:
    """Return True if the plan/major looks like CS or CSE."""
    return bool(plan and CS_CSE_REGEX.search(plan))


def filter_cs_cse_csv(text: str) -> str:
    """
    text: full contents of the uploaded CSV as a single string.
    returns: new CSV string with only CS/CSE rows.
    """
    # Wrap the text in a file-like object for DictReader
    input_io = io.StringIO(text)
    reader = csv.DictReader(input_io)

    # If CSV is empty or invalid, just return it
    if reader.fieldnames is None:
        return text

    output_io = io.StringIO()
    writer = csv.DictWriter(output_io, fieldnames=reader.fieldnames)
    writer.writeheader()

    for row in reader:
        major = (row.get("Program and Plan") or "").strip()
        if not is_cs_or_cse(major):
            continue
        writer.writerow(row)

    return output_io.getvalue()

def parse_roster_for_major_map(file_stream: TextIO) -> dict:
    """
    Parses a CSV file stream to map a student's official ID to their major.

    Args:
        file_stream: A text-based file stream of the CSV data.

    Returns:
        A dictionary mapping the student ID (ASURITE) to their major.
        Example: {"student12": "CS/CSE"}
    """
    student_major_map = {}
    
    reader = csv.DictReader(file_stream)
    for row in reader:
        major_plan = (row.get("Program and Plan") or "").strip()
        
        if is_cs_or_cse(major_plan):
            # Use the 'ASURITE' column from the CSV as the key, as it contains the login id we can use to match
            if student_id := row.get("ASURITE"):
                student_major_map[student_id.strip()] = "CS/CSE"
                
    return student_major_map