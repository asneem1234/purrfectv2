# Bot.py Documentation

## Overview

The `bot.py` file contains the implementation of Pawfessor Meowkins, an AI tutor cat that provides interactive learning experiences. This file defines a Flask blueprint and various helper functions for managing conversations, PDF processing, content retrieval, and generating teaching responses.

## Flask Blueprint

```python
bot_bp = Blueprint('bot_bp', __name__)
```

The file creates a Flask blueprint named `bot_bp` that can be registered with the main Flask application to handle bot-related routes.

## Global State Management

```python
# Store conversation context
conversation_contexts = {}
pdf_progress = {}
```

The file uses two dictionaries to manage state:
- `conversation_contexts`: Stores the context of ongoing conversations with users
- `pdf_progress`: Tracks progress when users are learning from PDF documents

## Core Helper Functions

### PDF Processing

#### `extract_text_from_pdf(pdf_file)`

Extracts text content from an uploaded PDF file.

**Parameters:**
- `pdf_file`: The uploaded PDF file object

**Returns:**
- A string containing the extracted text from all pages of the PDF

#### `manage_pdf_progress(session_id, action, content=None, response=None, topic=None)`

Manages the progress through a PDF document for a specific session.

**Parameters:**
- `session_id`: Unique identifier for the user session
- `action`: One of 'init', 'get', 'update', 'advance'
- `content`: The PDF content (for 'init')
- `response`: The AI response to store (for 'update')
- `topic`: The PDF topic name (for 'init')

**Returns:**
- Depends on action - chunk of text, progress info, etc.

### Content Retrieval

#### `retriever_tool(query, session_id=None)`

Simple search function to find relevant content from conversations.

**Parameters:**
- `query`: The search query text
- `session_id`: Optional session identifier to limit search scope

**Returns:**
- List of relevant text chunks that match the query

### Document Processing

#### `roadmap_tool(document, session_id=None)`

Creates a teaching roadmap from a document by chunking it into sections based on headers.

**Parameters:**
- `document`: The document text to process
- `session_id`: Optional session identifier

**Returns:**
- A dictionary containing sections, each with a title and chunks of content

#### `summarizer_tool(chunks)`

Summarizes chunks of content to create concise teaching points.

**Parameters:**
- `chunks`: Text content or list of chunks to summarize

**Returns:**
- A string containing a bullet-point summary of key concepts

### AI Response Generation

#### `generate_teaching_response(content, content_type, previous_context=None, session_id=None)`

The core function that generates AI teaching responses based on different content types.

**Parameters:**
- `content`: The content to process (topic, question, PDF content, etc.)
- `content_type`: The type of content ('init_study_session', 'chat', 'pdf', 'pdf_continuation', 'code', 'continuation', 'question')
- `previous_context`: Optional previous context for continuing conversations
- `session_id`: Optional session identifier

**Returns:**
- AI-generated response formatted according to the content type

### Gemini Model Integration

#### `get_gemini_model()`

Creates and returns an instance of the Gemini generative AI model.

**Returns:**
- A configured GenerativeModel instance from the Google Generative AI library

## Content Type Handling

The `generate_teaching_response` function handles various content types:

### 1. `init_study_session`

Initiates a new study session on a specified subject with an engaging introduction.

### 2. `chat`

Processes user chat messages and determines if they're study-related, casual, or inappropriate.

### 3. `pdf`

Handles new PDF document uploads by extracting the topic, creating a roadmap, and providing an initial explanation.

### 4. `pdf_continuation`

Continues teaching from a PDF document by advancing to the next chunk or section.

### 5. `code`

Analyzes and explains code snippets with teaching points about programming concepts.

### 6. `continuation`

Continues teaching about a previous topic with a logical progression of concepts.

### 7. `question`

Processes user questions about specific topics and provides relevant answers.

## Response Format

All responses follow a consistent JSON structure:

```json
{
  "response": "The explanation text",
  "buttons": ["Continue Learning", "I Have a Question"],
  "context": {
    "current_section": "Introduction",
    "next_section": "Core Concepts"
  }
}
```

This structure allows the frontend to render:
- The main teaching content
- Interactive buttons for the user to choose the next action
- Context for maintaining the learning flow

## Teaching Approach

Pawfessor Meowkins uses the ReAct framework for generating explanations:
1. **Reason**: Consider what concepts the student needs to understand
2. **Act**: Organize these concepts into a clear explanation
3. **Observe**: Ensure the explanation is appropriate for the context
4. **Final Answer**: Deliver an engaging explanation

The bot maintains a warm, friendly, and encouraging personality with cat-themed references throughout the teaching process.

## Security and Content Moderation

The bot includes guardrails to:
- Validate subject appropriateness
- Check subject specificity
- Ensure educational focus
- Handle inappropriate requests by redirecting to safe educational alternatives
