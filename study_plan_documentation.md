# Study Plan Module Documentation

This document explains the functionality of the `study_plan.py` module, which is responsible for creating, managing, and displaying AI-generated study plans in the Pawfessor Meowkins application.

## Overview

The Study Plan module creates personalized study schedules by analyzing PDF study materials using Gemini AI. It extracts key topics from the materials, prioritizes them, and creates a detailed day-by-day schedule based on user preferences and time constraints. The module includes features for:

- PDF text extraction and analysis
- AI-based topic extraction and prioritization
- Intelligent scheduling based on chronobiology principles
- Creation of detailed daily study plans with breaks and meals
- Saving, viewing, and managing study plans

## Blueprint Setup

```python
study_plan = Blueprint('study_plan', __name__, url_prefix='/studyplan')
```

The module uses Flask's Blueprint pattern with the prefix `/studyplan` for all routes.

## Core Functions

### PDF Processing Functions

#### `extract_text_from_pdf(pdf_file)`
- **Purpose**: Extracts text content from a PDF file
- **Parameters**: `pdf_file` - A file object containing the PDF
- **Returns**: String containing all extracted text
- **Details**: Uses PyPDF2 to read and extract text from each page of the PDF

#### `process_pdf_files(pdf_files)`
- **Purpose**: Processes multiple PDF files uploaded by the user
- **Parameters**: `pdf_files` - List of file objects from the request
- **Returns**: Tuple containing (combined text content, list of document dictionaries, collection name)
- **Details**: 
  - Extracts text from each PDF
  - Creates metadata for each document
  - Generates a collection name based on file names

### AI-Based Analysis Functions

#### `extract_important_topics(pdf_text)`
- **Purpose**: Uses Gemini AI to analyze PDF content and extract important study topics
- **Parameters**: `pdf_text` - String containing text extracted from PDFs
- **Returns**: Dictionary with a list of topic objects
- **Details**: 
  - Each topic includes:
    - Name
    - Importance score (1-10)
    - Explanation of why it's important
    - Recommended study time in minutes
    - Key points to focus on

#### `create_enhanced_study_schedule(form_data, topics_data)`
- **Purpose**: Creates an intelligent study schedule based on user preferences and topics
- **Parameters**: 
  - `form_data` - User preferences from form (dates, times, etc.)
  - `topics_data` - Topics extracted by the AI
- **Returns**: Dictionary with day-by-day schedule and plan summary
- **Details**:
  - Analyzes start and exam dates
  - Distributes study days evenly
  - Creates detailed daily schedules with activities
  - Implements the ReAct (Reasoning + Acting) framework

### Schedule Creation Helper Functions

#### `distribute_days_evenly(start_date, end_date, num_days)`
- **Purpose**: Distributes study days evenly between start and end dates
- **Parameters**:
  - `start_date` - Study preparation start date
  - `end_date` - Exam date
  - `num_days` - Number of study days needed
- **Returns**: List of datetime objects representing study days
- **Details**: Ensures balanced distribution of study days across the available time period

#### `create_fallback_activities(topics, day_idx, form_data)`
- **Purpose**: Creates backup schedule activities when AI scheduling fails
- **Parameters**:
  - `topics` - List of topics to study
  - `day_idx` - Index of the current day
  - `form_data` - User preferences
- **Returns**: List of activities for the day
- **Details**: Creates a balanced schedule with study sessions, breaks, and meals

### Route Handlers

#### `/forms` (GET)
- **Purpose**: Displays the form for creating a new study plan
- **Response**: Renders `forms.html` template

#### `/create-study-plan` (POST)
- **Purpose**: Processes form submission to create a study plan
- **Details**:
  - Extracts form data (exam details, preferences)
  - Processes uploaded PDFs
  - Extracts topics using Gemini AI
  - Creates study schedule
  - Stores plan in session
  - Redirects to study plan list

#### `/studyplan` (GET)
- **Purpose**: Displays newly created or saved study plans
- **Details**:
  - If a plan exists in session, displays it and removes from session
  - Otherwise, displays list of all saved plans

#### `/studyplan/<plan_id>` (GET)
- **Purpose**: Displays a specific saved study plan
- **Parameters**: `plan_id` - ID of the study plan to view
- **Details**: Retrieves plan from database, verifies ownership, and renders template

#### `/api/save_study_plan` (POST)
- **Purpose**: API endpoint to save a study plan to the database
- **Details**:
  - Receives JSON data with plan details
  - Creates new StudyPlan record
  - Returns success response with redirect URL

#### `/studyplan/live/<plan_id>` (GET)
- **Purpose**: Displays interactive version of a study plan
- **Parameters**: `plan_id` - ID of the study plan to view
- **Details**: Renders a special template for active use of the plan

#### `/studyplan/delete/<plan_id>` (GET, POST)
- **Purpose**: Deletes a study plan
- **Parameters**: `plan_id` - ID of the study plan to delete
- **Details**: Verifies ownership, deletes plan, and redirects to dashboard

### Helper Functions

#### `prepare_study_plan_data_for_template(topics, schedule)`
- **Purpose**: Prepares study plan data for template rendering
- **Parameters**:
  - `topics` - List of study topics
  - `schedule` - List of day schedules
- **Returns**: Dictionary with formatted data for templates
- **Details**: Converts data to JSON strings and creates human-readable versions

#### `get_study_plan_data_for_dashboard(active_plan_id=None)`
- **Purpose**: Retrieves study plan data for dashboard display
- **Parameters**: `active_plan_id` - Optional ID of active plan
- **Returns**: Dictionary with various plan lists and calendar data
- **Details**: 
  - Gets active, ongoing, upcoming, and past plans
  - Formats plans for calendar view
  - Handles errors with fallback data

## Database Model

The Study Plan module uses the `StudyPlan` model defined in `models.py` with the following fields:

- `id`: Primary key
- `user_id`: Foreign key to user who owns the plan
- `title`: Plan title
- `plan_summary`: Brief description of the plan
- `topics`: JSON text field storing topics data
- `detailed_schedule`: JSON text field storing the complete schedule
- `exam_date`: Date of the exam
- `prep_start_date`: Date to start preparation
- `is_revision_only`: Boolean flag for revision-only plans
- `form_inputs_json`: JSON text field storing original form data

## Key Features

1. **AI-Powered Topic Extraction**: Uses Gemini AI to identify important topics from study materials
2. **Chronobiology-Based Scheduling**: Creates schedules based on optimal study times
3. **Personalized Plans**: Adapts to user preferences and time constraints
4. **Interactive Viewing**: Provides multiple views for study plans
5. **Calendar Integration**: Shows plans on a calendar for better visualization
6. **Fallback Mechanisms**: Includes multiple fallback strategies for reliability

## Error Handling

The module implements extensive error handling to ensure reliability:
- PDF processing errors are caught and fallback content is used
- Date parsing issues are handled with alternative formats
- Schedule creation failures use a fallback scheduling mechanism
- Database operations are wrapped in try-except blocks
- A minimal fallback schedule is provided as a last resort

## Dependencies

- Flask and Blueprint for routing
- SQLAlchemy for database operations
- PyPDF2 for PDF text extraction
- Gemini AI for topic extraction and analysis
- JSON for data serialization/deserialization
- Datetime for date/time handling
