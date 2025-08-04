# Purrfect Project Structure Documentation

This document provides a comprehensive overview of all files and directories in the Purrfect project, explaining their purpose and functionality.

## Root Directory

### Main Application Files

- **app1.py**: Main application entry point. Sets up Flask application, configures database connections, registers blueprints, and initializes the app with all required settings. Contains session configuration, database setup (PostgreSQL with SQLite fallback), ChromaDB configuration, and blueprint registration.

- **db.py**: Database initialization and configuration module. Contains functions to set up SQLAlchemy and create tables based on models.

- **models.py**: Defines database models using SQLAlchemy ORM. Contains User, StudyPlan, ExamPlan, StudyRoom, UserLog, and other models representing the application's data structure.

- **routes.py**: Contains main application routes that aren't organized into blueprints, such as static page routes.

- **session_config.py**: Configures Flask session management, including session lifetime, security settings, and storage options.

- **planning.py**: Contains planning functionality for study plans and exam preparation that's not blueprint-specific.

- **migrate_exams.py**: Script for migrating exam data from one format to another, likely used during database schema updates.

- **password_migration.py**: Tool for migrating user passwords when changing the hashing algorithm or during data migration.

- **reset_passwords.py**: Utility script to reset user passwords, likely used for administrative purposes.

### Configuration Files

- **requirements.txt**: Lists all Python package dependencies required for the project, including specific versions.

- **Procfile**: Configuration file for Heroku deployment, specifies web server command.

- **render.yaml**: Configuration file for Render deployment platform.

- **.env**: (Not shown but likely exists) Environment variables configuration file.

### Documentation

- **LICENSE**: Project license file specifying the terms of use.

- **README.md**: Project overview, setup instructions, and general documentation.

- **project_structure.md**: This document, providing a detailed explanation of all project files.

## Blueprints Directory

The `blueprints` directory organizes the application into modular components, each handling a specific feature set.

- **__init__.py**: Initializes the blueprints package, allowing imports from the directory.

- **auth.py**: Authentication blueprint containing routes and logic for user registration, login, and logout functionality.

- **bot.py**: Implements the chat bot functionality for general study assistance.

- **dashboard.py**: Contains routes and logic for the main user dashboard, displaying study plans, progress, and upcoming exams.

- **exambot.py**: Specialized bot for exam preparation and practice questions.

- **flashcard.py**: Implements flashcard functionality for study aid and memorization.

- **game.py**: Educational games and gamification features for learning.

- **main.py**: Main blueprint containing general routes like landing page, about, etc.

- **notes.py**: Note-taking functionality for students to record their learning.

- **progress.py**: Student progress tracking and reporting features.

- **study_plan.py**: Study plan creation, management, and execution.

- **studyroom.py**: Virtual study rooms for collaborative learning.

- **purrrag_routes.py**: Routes for the PurrRAG (Purr Retrieval Augmented Generation) system, providing an AI-powered educational assistance interface.

## Static Directory

The `static` directory contains static assets used by the application.

### Images Directory

- Various image files used throughout the application, including logos, icons, and UI elements.

### JS Directory

- JavaScript files for client-side functionality, including interactive features, AJAX calls, and UI enhancements.

## Templates Directory

The `templates` directory contains HTML templates used by Flask to render pages.

- **bot.html**: Template for the chat bot interface.

- **coming-soon.html**: Placeholder for features that are under development.

- **create_room.html**: Form template for creating new study rooms.

- **create-note.html**: Form template for creating new notes.

- **dashboard.html**: Main user dashboard template displaying study plans, progress, and upcoming exams.

- **exam_plan_creator.html**: Interface for creating personalized exam preparation plans.

- **exambot.html**: Interface for the exam preparation bot.

- **features.html**: Overview of application features.

- **flashcard.html**: Template for displaying and interacting with flashcards.

- **flashcardgenerator.html**: Interface for creating new flashcards.

- **forms.html**: Reusable form components used across the application.

- **game.html**: Template for educational games.

- **landingpage.html**: Main landing page for non-authenticated users.

- **login.html**: User login form template.

- **notes-coming-soon.html**: Placeholder for notes feature that's under development.

- **planning.html**: Study planning interface.

- **profile.html**: User profile management template.

- **progress.html**: Student progress reporting and visualization template.

- **register.html**: User registration form template.

- **room_list.html**: List view of available study rooms.

- **studyplan_live.html**: Active study plan execution interface.

- **studyplan.html**: Study plan management interface.

- **studyroom.html**: Virtual study room interface for collaborative learning.

- **purrrag.html**: Interface for interacting with the PurrRAG system.

## Uploads Directory

The `uploads` directory stores user-uploaded files, primarily educational materials and documents. These files include:

- Academic PDFs for various courses (e.g., `AWS-Module-4.pdf`, `BCC_-_VIT_AP.pdf`)
- Research papers (e.g., `attention_is_all_you_need.pdf`, `Gradient_Based_Learning.pdf`)
- Lecture notes (e.g., `FALLSEM2024-25_CSE4001_TH_AP2024252001044_2024-07-26_Reference-Material-I.pdf`)
- Student submissions (e.g., `asneem_athar_shaik_22bce8807.pdf`)
- Project documentation (e.g., `AI-Powered_Study_Planner.pdf`)

These files are processed by the application for content extraction, indexing, and AI-assisted learning.

## Instance Directory

The `instance` directory contains instance-specific files that shouldn't be committed to version control:

- **app.db**: SQLite database file for local development.
- **app1.db**: Alternative SQLite database file, possibly used for testing.
- **Untitled-1.sqlite3-query**, **Untitled-2.sqlite3-query**: Database query files, likely used during development.

## Utils Directory

The `utils` directory contains utility functions and helper modules:

- **gemini_utils.py**: Utility functions for interacting with the Google Gemini API.

## PurrRAG Directory

The `purrrag` directory contains the custom Retrieval Augmented Generation system for educational applications:

### Root Directory

- **__init__.py**: Package initialization file.
- **main.py**: Main entry point for the PurrRAG system, providing the core functionality.
- **config.py**: Configuration management for PurrRAG.
- **README.md**: Documentation for the PurrRAG system.
- **requirements.txt**: Dependencies specific to the PurrRAG system.

### Knowledge Directory

- **document_processor.py**: Processes educational documents for indexing and knowledge extraction.
- **knowledge_graph.py**: Builds and maintains a knowledge graph of educational concepts.

### Learning Directory

- **student_profile.py**: Manages student profiles and learning states.
- **analytics.py**: Analyzes student learning patterns and provides insights.

### Retrieval Directory

- **vector_store.py**: Manages the vector database for semantic search using ChromaDB.
- **adaptive_retrieval.py**: Implements adaptive retrieval based on student profiles and context.

### Generation Directory

- **educational_response.py**: Generates educational responses tailored to student needs.
- **response_templates.py**: Manages templates for various types of educational responses.

### Integrations Directory

- **flask_integration.py**: Provides integration with the Flask web framework.

### Templates Directory

- **default_response.json**: Template for standard educational responses.
- **study_guide.json**: Template for generating study guides.
- **concept_explanation.json**: Template for explaining complex concepts.

### Examples Directory

- Contains example use cases and demonstrations of the PurrRAG system.

## ChronaDB Directory

The `chroma_db` directory contains the ChromaDB vector database files:

- **chroma.sqlite3**: Main database file for the vector database.

## __pycache__ Directory

Contains compiled Python bytecode files for faster loading:

- Various `.pyc` files corresponding to Python modules in the project.

## Integration Files

- **purrrag_integration.py**: Integration layer between PurrRAG and the main application.
- **purrrag_config.json**: Configuration file for the PurrRAG system.
- **setup_purrrag.py**: Setup script to initialize PurrRAG and process initial documents.

## Database Files

- **app.db**: Main SQLite database file (when not using PostgreSQL).

## Summary of Main Components

1. **Web Application**: Flask-based web application with various features for education and studying.
2. **Database**: SQL database (PostgreSQL or SQLite) for storing user data, study plans, etc.
3. **Vector Database**: ChromaDB for storing and retrieving vector embeddings for semantic search.
4. **Blueprints**: Modular components for different features of the application.
5. **AI Components**: PurrRAG system for AI-assisted learning and intelligent educational responses.
6. **User Interface**: HTML templates with JavaScript for frontend functionality.

The application uses a combination of traditional database storage with modern AI capabilities to provide an enhanced educational experience for users.
