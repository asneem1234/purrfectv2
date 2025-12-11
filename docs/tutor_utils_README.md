# Pawfessor Meowkins Tutor Agent Utilities

This module provides utility functions for the Pawfessor Meowkins Tutor Agent, enabling document processing, embedding generation, semantic retrieval, and teaching roadmap creation.

## Features

- Document chunking with sliding window and overlap
- Embedding generation using `all-MiniLM-L6-v2` model
- Vector storage and retrieval via Qdrant
- Teaching roadmap generation from document structure
- Content summarization for teaching

## Installation

1. Install the required dependencies:

```bash
pip install -r utils/tutor_requirements.txt
```

2. Initialize the Qdrant collections:

```bash
python utils/init_tutor_utils.py
```

For remote Qdrant server:

```bash
python utils/init_tutor_utils.py --url http://your-qdrant-server:6333
```

## Usage

### Document Processing

```python
from utils.tutor_utils import chunk_document, embed_chunks

# Split document into chunks
document_text = "Your document text here..."
chunks = chunk_document(document_text, chunk_size=500, overlap=50)

# Generate and store embeddings
doc_id = "unique_document_id"
embedded_chunks = embed_chunks(chunks, doc_id=doc_id)
```

### Semantic Retrieval

```python
from utils.tutor_utils import retriever_tool

# Retrieve relevant chunks for a query
query = "What is machine learning?"
results = retriever_tool(query, doc_id="unique_document_id", top_k=3)

for result in results:
    print(f"Score: {result['score']}, Content: {result['content'][:100]}...")
```

### Teaching Roadmap

```python
from utils.tutor_utils import roadmap_tool

# Create a teaching roadmap from document
document_text = "Your document text here..."
roadmap = roadmap_tool(document_text, doc_id="unique_document_id")

for section in roadmap["sections"]:
    print(f"Section: {section['section']}")
    print(f"Chunk IDs: {section['chunk_ids']}")
```

### Content Summarization

```python
from utils.tutor_utils import summarizer_tool

# Summarize chunks for teaching
chunks = [...]  # List of chunk dictionaries
summary = summarizer_tool(chunks)
print(summary)
```

## Integration with the Tutor Agent

The utility functions are designed to work with the Pawfessor Meowkins Tutor Agent. The integration is handled through the `bot.py` file, where the functions are used to enhance the teaching experience.

## Testing

Run the test script to verify the functionality:

```bash
python utils/test_tutor_utils.py
```

## LLM Integration

The utilities include a placeholder `call_llm(prompt)` function for making calls to language models. Replace this function with your preferred LLM API logic for roadmap generation and summarization tasks.
