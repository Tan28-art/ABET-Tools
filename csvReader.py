#checks for both cs and cse
import csv, re

#return true if major or plan looks like cs or cse
CS_CSE_REGEX = re.compile(
    r"""
    (?:\bcomputer\s+science\b)      |   # "Computer Science"
    (?:\bcomputer\s+sci\b)          |   # "Computer Sci" abbrev
    (?:\bcomputer\s+systems\s+eng)  |   # "Computer Systems Eng(r/ineering)"
    (?:\bcse\b)                         # "CSE" acronym
    """,
    re.IGNORECASE | re.VERBOSE
)

def is_cs_or_cse(plan: str) -> bool:
    return bool(plan and CS_CSE_REGEX.search(plan))

filename = input("Enter CSV filename: ").strip()

#make python dict then pull info with given keys from headers
with open(filename, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        major = (row.get("Program and Plan") or "").strip()
        if not is_cs_or_cse(major):
            continue
        first = (row.get("First Name") or "").strip()
        last  = (row.get("Last Name")  or "").strip()
        print(f"{first} {last} - {major}")
