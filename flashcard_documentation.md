# Flashcard Module Documentation

## Overview

The `flashcard.py` module implements flashcard functionality for study aid and memorization within the Purrfect application. It provides features for generating flashcards from different sources (topics or PDFs) and in various formats (question-answer, term-definition, or bullet points) using Google's Generative AI (Gemini).

## Module Structure

```
blueprints/flashcard.py
```

The module is organized as a Flask Blueprint and includes:

- Helper functions for working with Gemini AI
- Flashcard generation functions
- Database storage functions
- Flask route handlers for the web interface

## Dependencies

- **Flask**: Web framework for route handling and template rendering
- **Flask-Login**: User authentication
- **PyPDF2**: PDF text extraction
- **Google Generative AI (Gemini)**: AI model for generating flashcard content
- **ChromaDB**: Vector database for storing flashcards
- **JSON**: For data serialization and parsing
- **UUID**: For generating unique identifiers
- **re**: Regular expressions for parsing AI responses

## Core Functions

### `get_gemini_model()`

**Purpose**: Creates and returns a Gemini model instance for AI-based content generation.

**Parameters**: None

**Returns**: 
- A `GenerativeModel` instance from the Gemini API

**Implementation Details**:
- Uses `gemini-2.0-flash` model for efficient text generation

### `generate_flashcards_with_gemini(topic, card_type, card_count, pdf_text='')`

**Purpose**: Generates flashcards using the Gemini AI model based on a topic or PDF content.

**Parameters**:
- `topic` (str): The subject for flashcard generation
- `card_type` (str): Type of flashcard - 'qna', 'definition', or 'bullet'
- `card_count` (int): Number of flashcards to generate
- `pdf_text` (str, optional): Text extracted from PDF for content-based generation

**Returns**:
- List of dictionaries, each representing a flashcard with appropriate fields based on the card type

**Implementation Details**:
- Determines the primary source (topic or PDF)
- Creates an appropriate prompt based on the flashcard type
- Sends the prompt to Gemini and processes the response
- Extracts and parses JSON from the response
- Implements fallback mechanisms for error handling

### `save_to_chroma(user_id, content_type, content_data, metadata=None)`

**Purpose**: Saves flashcards to ChromaDB for persistent storage and future retrieval.

**Parameters**:
- `user_id` (int/str): User identifier for associating flashcards with a specific user
- `content_type` (str): Type of content being saved (typically 'flashcards')
- `content_data` (dict/list): The flashcard data to store
- `metadata` (dict, optional): Additional metadata for the flashcards

**Returns**:
- `bool`: True if successful, False otherwise

**Implementation Details**:
- Creates a collection specific to the user and content type
- Converts content data to string format if needed
- Generates a unique ID for the content
- Adds the flashcards to the collection with associated metadata
- Handles exceptions with detailed error logging

## Route Handlers

### `@flashcard_bp.route('/flashcardgenerator')`
### `def flashcardgenerator()`

**Purpose**: Renders the flashcard generator page.

**Authentication**: Requires user login

**Response**: Renders the 'flashcardgenerator.html' template

### `@flashcard_bp.route('/generate-flashcards', methods=['POST'])`
### `def generate_flashcards()`

**Purpose**: Processes form data and generates flashcards.

**Authentication**: Requires user login

**Request Parameters**:
- `sourceType`: 'topic' or 'pdf'
- `topic`: Subject for flashcards
- `cardCount`: Number of flashcards to generate
- `cardType`: Type of flashcards ('qna', 'definition', or 'bullet')
- `pdfUpload`: PDF file (if sourceType is 'pdf')

**Implementation Details**:
- Processes the form data
- Extracts text from PDF if provided
- Generates flashcards using Gemini AI
- Stores results in session
- Redirects to flashcard view

**Response**: Redirects to 'flashcard.flashcard_view' or back to generator on error

### `@flashcard_bp.route('/flashcard')`
### `def flashcard_view()`

**Purpose**: Displays generated flashcards to the user.

**Authentication**: Requires user login

**Session Data Used**:
- `flashcards`: List of flashcard dictionaries
- `flashcard_topic`: Topic of the flashcards
- `flashcard_type`: Type of flashcards

**Response**: Renders the 'flashcard.html' template with flashcard data

### `@flashcard_bp.route('/save-flashcards', methods=['POST'])`
### `def save_flashcards()`

**Purpose**: Saves the current set of flashcards to the database.

**Authentication**: Requires user login

**Request Data**:
- JSON payload with `flashcards`, `topic`, and `card_type` (optional)
- Falls back to session data if not provided in request

**Implementation Details**:
- Retrieves flashcard data from request or session
- Creates metadata for storage
- Saves to ChromaDB
- Returns status as JSON response

**Response**: JSON response indicating success or failure

### `@flashcard_bp.route('/reset-flashcards')`
### `def reset_flashcards()`

**Purpose**: Clears flashcard data from the session.

**Authentication**: Requires user login

**Implementation Details**:
- Removes flashcard-related data from session
- Adds a confirmation message
- Redirects to generator page

**Response**: Redirects to 'flashcard.flashcardgenerator'

## Error Handling

The module implements comprehensive error handling:

1. **JSON Parsing Errors**: Falls back to regex-based extraction or returns sample flashcards
2. **PDF Processing Errors**: Displays appropriate error messages to the user
3. **AI Generation Errors**: Provides fallback flashcards if Gemini fails
4. **Database Errors**: Returns error responses with details for debugging

## Session Management

The module uses Flask's session to store:

- Generated flashcards
- Flashcard topic
- Flashcard type
- JSON string representation of flashcards

This allows users to navigate between pages without losing their generated content.

## Logging

Extensive logging is implemented throughout the module for debugging and monitoring:

- AI prompt and response logging
- PDF processing information
- Error tracebacks
- Content validation checks

## Database Integration

The module integrates with ChromaDB, a vector database for storing and retrieving content:

- Creates user-specific collections
- Stores flashcards with detailed metadata
- Uses embedding functions for semantic search capabilities
- Handles database errors gracefully
