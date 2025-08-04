"""
Utility functions for Pawfessor Meowkins Tutor Agent.
Handles document chunking, embeddings, retrieval, and teaching roadmaps.
"""

import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Global constants
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_COLLECTION = "tutor_chunks"
VECTOR_SIZE = 384  # Size of embeddings for all-MiniLM-L6-v2

# Initialize the embedding model
_model = None

def get_embedding_model():
    """Lazy-load the embedding model to avoid loading it until needed."""
    global _model
    if _model is None:
        try:
            _model = SentenceTransformer(EMBEDDING_MODEL)
        except Exception as e:
            print(f"Error loading embedding model: {e}")
            raise
    return _model

def get_qdrant_client(url=None):
    """Get or create a Qdrant client.
    
    Args:
        url: Optional Qdrant server URL. If None, uses local in-memory storage.
    
    Returns:
        QdrantClient instance
    """
    try:
        if url:
            return QdrantClient(url=url)
        else:
            # Use in-memory storage by default
            return QdrantClient(":memory:")
    except Exception as e:
        print(f"Error connecting to Qdrant: {e}")
        raise

def ensure_collection_exists(client, collection_name=DEFAULT_COLLECTION):
    """Ensure that the Qdrant collection exists, creating it if needed.
    
    Args:
        client: QdrantClient instance
        collection_name: Name of the collection
    """
    try:
        collections = client.get_collections().collections
        collection_names = [collection.name for collection in collections]
        
        if collection_name not in collection_names:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
            print(f"Created collection '{collection_name}'")
        
        return True
    except Exception as e:
        print(f"Error ensuring collection exists: {e}")
        return False

def chunk_document(document_text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    """Split a document into overlapping chunks of text.
    
    Args:
        document_text: The full text of the document
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of dictionaries with chunk metadata:
        {
            "chunk_id": int,
            "content": str,
            "start_idx": int,
            "end_idx": int
        }
    """
    if not document_text or not isinstance(document_text, str):
        return []
    
    # Clean text - remove excessive whitespace
    document_text = re.sub(r'\s+', ' ', document_text).strip()
    
    chunks = []
    
    # If document is smaller than chunk size, return it as a single chunk
    if len(document_text) <= chunk_size:
        chunks.append({
            "chunk_id": 0,
            "content": document_text,
            "start_idx": 0,
            "end_idx": len(document_text)
        })
        return chunks
    
    # Create chunks with sliding window
    start_idx = 0
    chunk_id = 0
    
    while start_idx < len(document_text):
        end_idx = min(start_idx + chunk_size, len(document_text))
        
        # If not at the beginning, try to find a good split point
        if start_idx > 0:
            # Look for natural break points (paragraph, sentence, space)
            paragraph_break = document_text.rfind('\n\n', start_idx, end_idx)
            sentence_break = document_text.rfind('. ', start_idx, end_idx)
            space_break = document_text.rfind(' ', start_idx, end_idx)
            
            # Use the best break point available
            if paragraph_break != -1 and paragraph_break + 2 > start_idx + chunk_size / 4:
                end_idx = paragraph_break + 2
            elif sentence_break != -1 and sentence_break + 2 > start_idx + chunk_size / 4:
                end_idx = sentence_break + 2
            elif space_break != -1:
                end_idx = space_break + 1
        
        # Extract the chunk
        chunk_text = document_text[start_idx:end_idx].strip()
        
        # Only add non-empty chunks
        if chunk_text:
            chunks.append({
                "chunk_id": chunk_id,
                "content": chunk_text,
                "start_idx": start_idx,
                "end_idx": end_idx
            })
            chunk_id += 1
        
        # Move to the next chunk with overlap
        start_idx = end_idx - overlap
    
    return chunks

def embed_chunks(chunks: List[Dict[str, Any]], doc_id: str = None, collection_name: str = DEFAULT_COLLECTION, 
                client = None, url: str = None) -> List[Dict[str, Any]]:
    """Create embeddings for chunks and store them in Qdrant.
    
    Args:
        chunks: List of chunk dictionaries from chunk_document()
        doc_id: Unique identifier for the document. If None, generates a UUID
        collection_name: Name of the Qdrant collection to use
        client: Optional QdrantClient instance
        url: Optional Qdrant server URL
    
    Returns:
        List of chunks with embeddings
    """
    if not chunks:
        return []
    
    # Generate doc_id if not provided
    if doc_id is None:
        doc_id = str(uuid.uuid4())
    
    # Get the embedding model
    model = get_embedding_model()
    
    # Get or create the Qdrant client
    if client is None:
        client = get_qdrant_client(url)
    
    # Ensure collection exists
    ensure_collection_exists(client, collection_name)
    
    # Extract the text from each chunk for embedding
    texts = [chunk["content"] for chunk in chunks]
    
    try:
        # Generate embeddings for all texts at once
        embeddings = model.encode(texts)
        
        # Prepare points for Qdrant
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Add embedding to chunk metadata
            chunk["embedding"] = embedding.tolist()
            
            # Create a Qdrant point
            point_id = f"{doc_id}_{chunk['chunk_id']}"
            section = chunk.get("section", "")
            
            point = models.PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={
                    "doc_id": doc_id,
                    "chunk_id": chunk["chunk_id"],
                    "section": section,
                    "text": chunk["content"],
                    "start_idx": chunk["start_idx"],
                    "end_idx": chunk["end_idx"]
                }
            )
            points.append(point)
        
        # Upsert points into Qdrant
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        
        print(f"Embedded and stored {len(chunks)} chunks in collection '{collection_name}' with doc_id '{doc_id}'")
        return chunks
    except Exception as e:
        print(f"Error embedding chunks: {e}")
        return chunks

def retriever_tool(query: str, doc_id: str = None, top_k: int = 3, 
                  collection_name: str = DEFAULT_COLLECTION, client = None, url: str = None) -> List[Dict[str, Any]]:
    """Retrieve relevant chunks for a query using semantic search.
    
    Args:
        query: The user query
        doc_id: Optional document ID to filter results
        top_k: Number of results to return
        collection_name: Name of the Qdrant collection to use
        client: Optional QdrantClient instance
        url: Optional Qdrant server URL
    
    Returns:
        List of matching chunks with scores
    """
    if not query or not isinstance(query, str):
        return []
    
    # Get the embedding model
    model = get_embedding_model()
    
    # Get or create the Qdrant client
    if client is None:
        client = get_qdrant_client(url)
    
    try:
        # Ensure collection exists
        if not ensure_collection_exists(client, collection_name):
            return []
        
        # Generate embedding for the query
        query_embedding = model.encode(query)
        
        # Prepare search filters
        search_filter = None
        if doc_id:
            search_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id)
                    )
                ]
            )
        
        # Search in Qdrant
        search_results = client.search(
            collection_name=collection_name,
            query_vector=query_embedding.tolist(),
            limit=top_k,
            filter=search_filter
        )
        
        # Extract and format results
        results = []
        for hit in search_results:
            results.append({
                "chunk_id": hit.payload.get("chunk_id"),
                "doc_id": hit.payload.get("doc_id"),
                "content": hit.payload.get("text"),
                "section": hit.payload.get("section", ""),
                "score": hit.score,
                "start_idx": hit.payload.get("start_idx"),
                "end_idx": hit.payload.get("end_idx")
            })
        
        return results
    except Exception as e:
        print(f"Error in retriever_tool: {e}")
        return []

def call_llm(prompt: str) -> str:
    """Placeholder for LLM API calls.
    
    Args:
        prompt: The prompt to send to the LLM
    
    Returns:
        Generated text response
    """
    # This is just a placeholder - implement actual LLM call logic
    print(f"LLM prompt: {prompt[:100]}...")
    return "LLM response placeholder"

def extract_sections_from_document(document_text: str) -> List[Dict[str, Any]]:
    """Extract section headers from document text.
    
    Args:
        document_text: The full text of the document
    
    Returns:
        List of identified sections with start positions
    """
    if not document_text:
        return []
    
    sections = []
    
    # Common section header patterns
    patterns = [
        # Markdown-style headers
        (r'#{1,6}\s+(.*?)(?:\n|$)', 1),
        # Underlined headers
        (r'([^\n]+)\n={3,}(?:\n|$)', 1),
        (r'([^\n]+)\n-{3,}(?:\n|$)', 1),
        # Numbered sections
        (r'(?:^|\n)(\d+(?:\.\d+)*)\s+(.*?)(?:\n|$)', 0),
        # Common section names
        (r'(?:^|\n)(Introduction|Background|Methodology|Results|Discussion|Conclusion)(?::|\s|$)', 1)
    ]
    
    for pattern, group in patterns:
        for match in re.finditer(pattern, document_text, re.MULTILINE):
            if group == 0:  # Full match
                title = match.group().strip()
            else:  # Specific capture group
                title = match.group(group).strip()
            
            sections.append({
                "title": title,
                "start_pos": match.start()
            })
    
    # Sort sections by their position in the document
    sections.sort(key=lambda x: x["start_pos"])
    
    return sections

def roadmap_tool(document_text: str, doc_id: str = None) -> Dict[str, Any]:
    """Create a teaching roadmap from a document.
    
    Args:
        document_text: The full text of the document
        doc_id: Optional document ID
    
    Returns:
        Dictionary with roadmap sections and their associated chunks
    """
    if not document_text:
        return {"sections": []}
    
    # Generate doc_id if not provided
    if doc_id is None:
        doc_id = str(uuid.uuid4())
    
    # First, chunk the document
    chunks = chunk_document(document_text)
    
    # Try to extract sections from the document structure
    extracted_sections = extract_sections_from_document(document_text)
    
    # If no sections found, create artificial ones or use LLM
    if not extracted_sections:
        # Use LLM to generate section titles
        prompt = f"""
        Extract 3-5 main section titles from this document that would be useful for teaching:
        
        {document_text[:5000]}
        
        Return only the section titles, one per line, with no additional text.
        """
        
        try:
            section_titles_text = call_llm(prompt)
            section_titles = [title.strip() for title in section_titles_text.split('\n') if title.strip()]
            
            # Create evenly spaced sections
            if section_titles:
                doc_length = len(document_text)
                sections_count = len(section_titles)
                
                for i, title in enumerate(section_titles):
                    start_pos = int((i / sections_count) * doc_length)
                    extracted_sections.append({
                        "title": title,
                        "start_pos": start_pos
                    })
            else:
                # Fallback: create generic sections
                extracted_sections = [
                    {"title": "Introduction", "start_pos": 0},
                    {"title": "Main Content", "start_pos": len(document_text) // 3},
                    {"title": "Conclusion", "start_pos": len(document_text) * 2 // 3}
                ]
        except Exception as e:
            print(f"Error generating section titles: {e}")
            # Fallback to generic sections
            extracted_sections = [
                {"title": "Introduction", "start_pos": 0},
                {"title": "Main Content", "start_pos": len(document_text) // 3},
                {"title": "Conclusion", "start_pos": len(document_text) * 2 // 3}
            ]
    
    # Associate chunks with sections
    roadmap = {"sections": []}
    
    for i, section in enumerate(extracted_sections):
        section_chunks = []
        section_title = section["title"]
        section_start = section["start_pos"]
        
        # Find the end position of this section
        if i < len(extracted_sections) - 1:
            section_end = extracted_sections[i + 1]["start_pos"]
        else:
            section_end = len(document_text)
        
        # Find chunks that belong to this section
        for chunk in chunks:
            # Check if the chunk overlaps with this section
            if (chunk["start_idx"] >= section_start and chunk["start_idx"] < section_end) or \
               (chunk["end_idx"] > section_start and chunk["end_idx"] <= section_end) or \
               (chunk["start_idx"] <= section_start and chunk["end_idx"] >= section_end):
                # Add section info to the chunk
                chunk["section"] = section_title
                section_chunks.append(chunk["chunk_id"])
        
        # Add the section to the roadmap
        roadmap["sections"].append({
            "section": section_title,
            "chunk_ids": section_chunks
        })
    
    # Ensure all chunks have section assigned
    for chunk in chunks:
        if "section" not in chunk:
            # Find the nearest section
            min_distance = float('inf')
            nearest_section = "Unknown"
            
            for section in extracted_sections:
                distance = abs(chunk["start_idx"] - section["start_pos"])
                if distance < min_distance:
                    min_distance = distance
                    nearest_section = section["title"]
            
            chunk["section"] = nearest_section
    
    # If we have a doc_id, save the embeddings
    if doc_id:
        embed_chunks(chunks, doc_id)
    
    return roadmap

def summarizer_tool(chunks: List[Dict[str, Any]]) -> str:
    """Create a concise teaching summary from document chunks.
    
    Args:
        chunks: List of document chunks to summarize
    
    Returns:
        Concise teaching explanation string
    """
    if not chunks:
        return "No content to summarize."
    
    # Extract text from chunks
    texts = [chunk["content"] for chunk in chunks]
    combined_text = "\n\n".join(texts)
    
    # Limit text length for the LLM
    max_text_length = 8000
    if len(combined_text) > max_text_length:
        combined_text = combined_text[:max_text_length] + "..."
    
    # Create a prompt for the LLM
    prompt = f"""
    Create a clear, concise teaching explanation from this content. Focus on key concepts and important details:
    
    {combined_text}
    
    Write 2-3 paragraphs that:
    1. Introduce the main concepts
    2. Explain the key ideas in student-friendly language
    3. Highlight the most important points
    
    Keep your summary informative but engaging, as if teaching a student.
    """
    
    try:
        summary = call_llm(prompt)
        return summary
    except Exception as e:
        print(f"Error in summarizer_tool: {e}")
        # Create a basic summary as fallback
        first_chunk = chunks[0]["content"][:500]
        return f"This content covers: {first_chunk}..."
