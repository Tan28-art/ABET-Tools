"""
Configuration file for ABET Tools
Contains default settings and configuration options.
"""

# Canvas Configuration
CANVAS_DOMAIN = 'https://canvas.asu.edu'
DEFAULT_COURSE_ID = 240102

# Output Configuration
OUTPUT_DIRECTORY = './output'
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'

# API Configuration
REQUESTS_PER_PAGE = 100
REQUEST_TIMEOUT = 30

# File Naming
TIMESTAMP_FORMAT = '%Y%m%d_%H%M%S'
JSON_FILENAME_TEMPLATE = 'grades_data_{course_id}_{timestamp}.json'
CSV_FILENAME_TEMPLATE = 'grades_summary_{course_id}_{timestamp}.csv'
LOG_FILENAME = 'grades_fetch.log'

# Grade Analysis Configuration
INCLUDE_ANONYMOUS_SUBMISSIONS = False
INCLUDE_UNGRADED_SUBMISSIONS = True
CALCULATE_STATISTICS = True
