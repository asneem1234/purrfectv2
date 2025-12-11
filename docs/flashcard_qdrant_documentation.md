# Flashcard Module Documentation - Qdrant Version

## Overview

The `flashcard.py` module implements flashcard functionality for study aid and memorization within the Purrfect application. This version uses Qdrant Cloud for vector database storage, allowing for semantic search and efficient retrieval of flashcards.

## Key Features

1. **AI-Generated Flashcards**: Uses Google's Generative AI (Gemini) to create flashcards from topics or PDF content
2. **Vector Database Storage**: Stores flashcards in Qdrant Cloud with vector embeddings for semantic search
3. **Multiple Flashcard Types**: Supports question-answer, term-definition, and bullet point formats
4. **Semantic Search**: Retrieves flashcards semantically relevant to natural language queries
5. **Hybrid Search**: Combines vector similarity with keyword matching for improved results
6. **Duplicate Prevention**: Detects and avoids storing duplicate flashcards using content hashing

## Module Structure

```
blueprints/flashcard.py
```

## Dependencies

- **Flask**: Web framework for route handling and template rendering
- **Flask-Login**: User authentication
- **PyPDF2**: PDF text extraction
- **Google Generative AI (Gemini)**: AI model for generating flashcard content
- **Sentence Transformers**: For creating vector embeddings from text
- **Qdrant Client**: Interface to the Qdrant vector database
- **UUID**: For generating unique identifiers
- **hashlib**: For content hashing and duplicate detection

## Environment Variables

- `QDRANT_URL`: URL to the Qdrant cloud service
- `QDRANT_API_KEY`: API key for authenticating with Qdrant

## Core Functions

### Qdrant Utilities

#### `get_collection_name(user_id)`

**Purpose**: Generates a standardized collection name for a user's flashcards.

**Parameters**:
- `user_id` (int/str): The user's identifier

**Returns**: 
- String in the format `flashcards_{user_id}`

#### `create_embedding(text)`

**Purpose**: Creates a vector embedding for the given text.

**Parameters**:
- `text` (str): Text to be embedded

**Returns**: 
- List of float values representing the embedding vector, or None if embedding fails

#### `create_collection(user_id, vector_size=384)`

**Purpose**: Creates a new Qdrant collection for storing flashcards.

**Parameters**:
- `user_id` (int/str): The user's identifier
- `vector_size` (int): Size of the embedding vectors (defaults to 384 for all-MiniLM-L6-v2)

**Returns**: 
- Boolean indicating success or failure

**Implementation Details**:
- Creates a collection with COSINE distance metric
- Sets up payload indexes for efficient filtering
- Configures immediate indexing for real-time search

#### `ensure_collection_exists(user_id)`

**Purpose**: Checks if a collection exists, creates it if it doesn't.

**Parameters**:
- `user_id` (int/str): The user's identifier

**Returns**: 
- Boolean indicating success or failure

#### `insert_flashcards(user_id, flashcards, metadata=None)`

**Purpose**: Inserts flashcards with embeddings into the Qdrant collection.

**Parameters**:
- `user_id` (int/str): The user's identifier
- `flashcards` (list): List of flashcard dictionaries
- `metadata` (dict): Additional metadata about the flashcards

**Returns**: 
- Boolean indicating success or failure

**Implementation Details**:
- Creates embeddings for each flashcard
- Uses content hashing to detect duplicates
- Generates deterministic UUIDs for deduplication
- Structures payload with all relevant metadata
- Inserts in batches for efficiency

#### `semantic_search(user_id, query, top_k=5, filters=None)`

**Purpose**: Searches for flashcards semantically similar to the query.

**Parameters**:
- `user_id` (int/str): The user's identifier
- `query` (str): Search query
- `top_k` (int): Maximum number of results to return
- `filters` (dict): Optional filters to narrow down results

**Returns**: 
- List of flashcard dictionaries with relevance scores

**Implementation Details**:
- Creates embedding for the search query
- Applies user_id filter for security
- Applies additional filters if specified
- Returns formatted results with relevance scores

#### `hybrid_search(user_id, query, top_k=5, filters=None)`

**Purpose**: Performs hybrid search combining vector similarity with keyword matching.

**Parameters**:
- `user_id` (int/str): The user's identifier
- `query` (str): Search query
- `top_k` (int): Maximum number of results to return
- `filters` (dict): Optional filters to narrow down results

**Returns**: 
- List of flashcard dictionaries with relevance scores

**Implementation Details**:
- Similar to semantic_search but with enhanced parameters
- Uses optimized HNSW parameters for better recall

### Gemini AI Integration

#### `get_gemini_model()`

**Purpose**: Creates and returns a Gemini model instance.

**Returns**: 
- A `GenerativeModel` instance from the Gemini API

#### `generate_flashcards_with_gemini(topic, card_type, card_count, pdf_text='')`

**Purpose**: Generates flashcards using the Gemini AI model.

**Parameters**:
- `topic` (str): Topic for flashcards
- `card_type` (str): Type of flashcards ('qna', 'definition', or 'bullet')
- `card_count` (int): Number of flashcards to generate
- `pdf_text` (str): Optional text extracted from a PDF

**Returns**: 
- List of flashcard dictionaries

**Implementation Details**:
- Determines the primary source (topic or PDF content)
- Creates an appropriate prompt based on the flashcard type
- Processes the AI response to extract valid JSON
- Includes fallback mechanisms for error handling

### Route Handlers

#### `/flashcardgenerator`

**Purpose**: Displays the flashcard generator page.

**Authentication**: Requires login

**Response**: Renders 'flashcardgenerator.html'

#### `/generate-flashcards` (POST)

**Purpose**: Processes user input and generates flashcards.

**Authentication**: Requires login

**Form Parameters**:
- `sourceType`: 'topic' or 'pdf'
- `topic`: Subject for flashcards
- `cardCount`: Number of flashcards
- `cardType`: Format of flashcards
- `difficulty`: Importance rating (1-10)
- `pdfUpload`: PDF file (if source is 'pdf')

**Implementation Details**:
- Extracts text from PDF if provided
- Generates flashcards with Gemini
- Automatically stores in Qdrant if available
- Saves to session for UI display

**Response**: Redirects to flashcard view page

#### `/flashcard`

**Purpose**: Displays the generated flashcards.

**Authentication**: Requires login

**Session Data Used**:
- `flashcards`: List of flashcards
- `flashcard_topic`: Topic
- `flashcard_type`: Type of flashcards

**Response**: Renders 'flashcard.html'

#### `/save-flashcards` (POST)

**Purpose**: Explicitly saves flashcards to Qdrant.

**Authentication**: Requires login

**Request Data**: JSON with flashcards, topic, and metadata

**Response**: JSON response indicating success or failure

#### `/reset-flashcards`

**Purpose**: Clears session data for flashcards.

**Authentication**: Requires login

**Response**: Redirects to generator page

#### `/api/search-flashcards` (POST)

**Purpose**: API endpoint for searching flashcards.

**Authentication**: Requires login

**Request Data**:
- `query`: Search query
- `search_type`: 'semantic' or 'hybrid'
- `top_k`: Maximum results
- Optional filters: `card_type`, `topic`, `difficulty`

**Response**: JSON with search results

#### `/search-flashcards`

**Purpose**: Renders the flashcard search page.

**Authentication**: Requires login

**Implementation Details**:
- Gathers available topics and card types for filters
- Renders the search interface template

**Response**: Renders 'flashcard_search.html'

## Error Handling

The module implements comprehensive error handling:

1. **Missing Dependencies**: Falls back to session-only storage if Qdrant or embedding model is unavailable
2. **JSON Parsing Errors**: Includes regex-based extraction as fallback
3. **Embedding Failures**: Logs errors and continues with available functionality
4. **Search Errors**: Returns empty results with appropriate error messages

## Session Management

The module uses Flask's session to store:

- Generated flashcards
- Flashcard topic
- Flashcard type
- Source type (topic or PDF)

## Duplicate Prevention

Multiple layers of duplicate detection:

1. **Content Hashing**: Creates MD5 hash of flashcard content
2. **Deterministic UUIDs**: Generates IDs based on content hash
3. **Batch Deduplication**: Tracks already processed hashes within a batch

## Vector Storage Schema

Each flashcard in Qdrant includes:

- **Vector**: Embedding from the Sentence Transformer model
- **Payload**:
  - `user_id`: User identifier
  - `card_type`: Format of the flashcard
  - `topic`: Subject of the flashcard
  - `difficulty`: Importance rating (1-10)
  - `source`: Origin of content ('topic' or 'pdf')
  - `content`: Full text content
  - `card_front`: Front-facing content
  - `card_back`: Back-facing content
  - `content_hash`: MD5 hash for deduplication
  - `timestamp`: Creation time
  - `raw_data`: Original flashcard object
