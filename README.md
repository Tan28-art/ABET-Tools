# ABET-Tools
Github Repo for the ABET Tools Capstone Project

## Getting Started
1. Clone repo
```
git clone https://github.com/your-username/ABET-Tools.git
cd ABET-Tools
```

2. create virtual env
```
python -m venv your-venv-name

# Activate venv
# For mac/linux
source ./your-venv-name/bin/activate

# for windows
source ./your-venv-name/Scripts/activate
```

3. Install Dependencies
```
pip install -r requirements.txt
```

4. Configure access token
```
export canvas_access_token="your canvas access token"
```

5. Run file
```
python test_script.py
```

## Grades Fetching

The project includes a comprehensive grades fetching system for Canvas LMS integration.

### Features
- Fetch all assignments for a course
- Retrieve student submissions and grades
- Generate grade statistics and summaries
- Export data to JSON and CSV formats
- Comprehensive logging and error handling

### Usage

#### Basic Test
```bash
python test_grades_fetch.py
```

#### Full Grades Fetch
```bash
python fetch_grades.py
```

### Output Files
- `grades_data_[course_id]_[timestamp].json` - Complete grades data in JSON format
- `grades_summary_[course_id]_[timestamp].csv` - Grade statistics in CSV format
- `grades_fetch.log` - Detailed logging information

### Configuration
Make sure your Canvas access token is set:
```bash
export canvas_access_token="your_canvas_access_token"
```

The script is configured to work with the ASU Canvas instance (`https://canvas.asu.edu`) and uses course ID `240102` by default.
