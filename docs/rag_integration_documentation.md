# RAG Integration for Study Plan Module

This document explains how the Study Plan module has been enhanced with Retrieval-Augmented Generation (RAG) capabilities using Qdrant Vector Database.

## Overview

The Study Plan module now includes a RAG layer that stores generated study plans in a vector database (Qdrant) for semantic retrieval. This allows students to ask questions about their study materials and get contextually relevant answers based on their personal study plans.

## Key Components

### 1. Embedding Generation

- Uses `sentence-transformers/all-MiniLM-L6-v2` for creating vector embeddings of study plan content
- Each topic, key point, and schedule activity is embedded separately for granular retrieval

### 2. Qdrant Integration

- Connects to Qdrant Cloud using environment variables:
  - `QDRANT_URL`: URL of the Qdrant cloud instance
  - `QDRANT_API_KEY`: API key for authentication

- Collection naming follows the pattern: `studyplan_{user_id}`

### 3. RAG Functions

#### Collection Management

- `create_collection(collection_name, vector_size=384)`: Creates or recreates a Qdrant collection with appropriate indexes
- `get_collection_name(user_id)`: Generates the standardized collection name for a user

#### Embedding and Storage

- `create_embedding(text)`: Creates vector embeddings for text using sentence-transformers
- `insert_document(plan_id, content, metadata, collection_name)`: Stores a document chunk with metadata in Qdrant
- `store_study_plan_in_qdrant(user_id, plan_id, topics, detailed_schedule)`: Processes and stores a complete study plan

#### Retrieval

- `semantic_search(query, collection_name, filters=None, top_k=5)`: Performs vector similarity search
- `hybrid_search(query, collection_name, filters=None, top_k=5)`: Combines vector and keyword search
- `query_study_plan(user_id, query, filters=None, top_k=5)`: High-level function for querying a user's study plans

### 4. Metadata Schema

Each document chunk stored in Qdrant includes the following metadata:

- `plan_id` (str): Links the chunk to a specific study plan
- `content` (str): The actual content chunk
- `topic` (str): The topic name
- `subtopic` (str): Subtopic or key point name (if applicable)
- `day` (str): Study day in the plan (if applicable)
- `importance` (int): Importance score from 1-10 (based on Gemini analysis)
- `type` (str): Type of content (roadmap_step | note | flashcard | schedule_activity)

### 5. Integration Points

- The RAG system is automatically used when saving a new study plan
- Content is chunked and stored with appropriate metadata
- A demo page at `/studyplan/rag-demo` allows testing the RAG capabilities
- An API endpoint at `/api/study-answer` provides question answering using RAG

## Usage Examples

### Storing a Study Plan in RAG

```python
# This happens automatically when a plan is saved
store_study_plan_in_qdrant(
    user_id=current_user.id,
    plan_id=plan.id,
    topics=plan.topics_data,
    detailed_schedule=plan.schedule_data
)
```

### Querying the Study Plan

```python
# Retrieve relevant chunks with filters
results = query_study_plan(
    user_id=current_user.id,
    query="What should I study today?",
    filters={"type": "schedule_activity"},
    top_k=5
)
```

### Generating an Answer with Context

The `study_answer_api` endpoint handles:
1. Retrieving relevant context using hybrid search
2. Passing the context to Gemini for answering
3. Falling back to direct generation if no context is available

## Fallback Mechanism

If Qdrant is not initialized or the collection is empty, the system falls back to direct Gemini generation without RAG context. This ensures that users always get a response, even if the RAG system is not available.

## Demo and Testing

The `/studyplan/rag-demo` route provides a web interface to:
- Check Qdrant connection status
- View collection statistics
- Initialize or reset the collection
- Search for content across study plans
- Test retrieval with example queries

## Security Considerations

- Qdrant connection details are read from environment variables for security
- Each user has their own isolated collection
- The Qdrant client initialization is wrapped in error handling to prevent crashes

## Performance Considerations

- Embeddings are generated at save time to avoid latency at query time
- Hybrid search combines vector similarity with keyword matching for better results
- Payload indexes on metadata fields enable efficient filtering
