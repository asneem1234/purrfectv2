from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, current_app
from flask_login import login_required, current_user
import os
from werkzeug.utils import secure_filename
import PyPDF2
import uuid
import datetime
import re
import json
import traceback
import google.generativeai as genai
import requests
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue
import numpy as np
from typing import List, Dict, Any, Optional, Union
import time
from dotenv import load_dotenv
import logging

# Create blueprint with proper name
bot_bp = Blueprint('bot_bp', __name__)

# Store conversation context (fallback mechanism)
conversation_contexts = {}
pdf_progress = {}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='purr_rag.log'
)
logger = logging.getLogger('purr_rag')

# Load environment variables
load_dotenv()

# Initialize Qdrant client
try:
    qdrant_url = os.environ.get('QDRANT_URL')
    qdrant_api_key = os.environ.get('QDRANT_API_KEY')
    
    if qdrant_url and qdrant_api_key:
        try:
            # Use cloud Qdrant if credentials are provided
            qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            # Test the connection
            qdrant_client.get_collections()
            logger.info("Qdrant cloud client initialized successfully")
        except Exception as cloud_err:
            logger.warning(f"Cloud Qdrant connection failed despite credentials: {str(cloud_err)}")
            raise  # Propagate to outer try/except to try local fallbacks
    else:
        # Fall back to local Qdrant instance or in-memory
        try:
            # First try connecting to a local Qdrant instance (useful for development)
            qdrant_client = QdrantClient(host="localhost", port=6333)
            # Test the connection
            qdrant_client.get_collections()
            logger.info("Connected to local Qdrant instance successfully")
        except Exception as local_err:
            # If local connection fails, use in-memory Qdrant
            logger.warning(f"Local Qdrant connection failed: {str(local_err)}")
            logger.info("Using in-memory Qdrant instance as fallback")
            try:
                qdrant_client = QdrantClient(":memory:")
                # Simple test to ensure the in-memory client works
                qdrant_client.get_collections()
                logger.info("In-memory Qdrant client initialized successfully")
            except Exception as mem_err:
                logger.error(f"In-memory Qdrant also failed: {str(mem_err)}")
                qdrant_client = None
except Exception as e:
    qdrant_client = None
    logger.error(f"Failed to initialize any Qdrant client: {str(e)}")

# Initialize embedding models
try:
    # Main embedding model for semantic search
    embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    
    # Cross-encoder for re-ranking
    cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    
    logger.info("Embedding models loaded successfully")
except Exception as e:
    embedding_model = None
    cross_encoder = None
    logger.error(f"Failed to load embedding models: {str(e)}")

# Helper functions for bot functionality

def extract_text_from_pdf(pdf_file):
    """Extract text from a PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            text += pdf_reader.pages[page_num].extract_text()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

def get_gemini_model():
    """Get the Gemini generative model"""
    return genai.GenerativeModel('gemini-2.0-flash')

def manage_pdf_progress(session_id, action, content=None, response=None, topic=None):
    """
    Manage the progress through a PDF document for a specific session
    
    Args:
        session_id: Unique identifier for the user session
        action: One of 'init', 'get', 'update', 'advance'
        content: The PDF content (for 'init')
        response: The AI response to store (for 'update')
        topic: The PDF topic name (for 'init')
    
    Returns:
        Depends on action - chunk of text, progress info, etc.
    """
    global pdf_progress
    
    # Initialize a new PDF reading session
    if action == 'init':
        # Default chunk size with a slight overlap
        chunk_size = 3000
        overlap = 500
        
        # Store full session information
        pdf_progress[session_id] = {
            "topic": topic or "PDF Document",
            "content": content,
            "offset": 0,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "previous_responses": [],
            "extracted_topics": [],  # Store key topics found so far
            "current_section": "Introduction"  # Estimate the current section
        }
        
        # Return the initial chunk
        return content[:chunk_size]
    
    # Get the current progress information
    elif action == 'get':
        if session_id not in pdf_progress:
            return None
        return pdf_progress[session_id]
    
    # Update progress after a continuation
    elif action == 'update':
        if session_id in pdf_progress:
            # Store the response
            if response:
                pdf_progress[session_id]["previous_responses"].append(response)
                
                # Limit stored responses to prevent context size issues
                if len(pdf_progress[session_id]["previous_responses"]) > 5:
                    pdf_progress[session_id]["previous_responses"] = pdf_progress[session_id]["previous_responses"][-5:]
            
            return True
        return False
    
    # Advance to the next chunk of the PDF
    elif action == 'advance':
        if session_id in pdf_progress:
            info = pdf_progress[session_id]
            
            # Calculate the next position with overlap
            next_offset = info["offset"] + info["chunk_size"] - info["overlap"]
            
            # Don't go beyond the end of the content
            if next_offset >= len(info["content"]):
                # If we're at the end, return a smaller final chunk or None
                if info["offset"] + 100 >= len(info["content"]):
                    return None  # No more content
                else:
                    # Return the final chunk
                    final_chunk = info["content"][info["offset"]:]
                    pdf_progress[session_id]["offset"] = len(info["content"])
                    return final_chunk
            
            # Update offset and return the next chunk
            pdf_progress[session_id]["offset"] = next_offset
            next_chunk = info["content"][next_offset:next_offset + info["chunk_size"]]
            
            # Try to estimate the current section based on headings in the chunk
            section_patterns = [
                r'#+\s+(.*?)\n',  # Markdown style headers
                r'(.*?)\n[=\-]{3,}',  # Underlined headers
                r'(?i)^(?:chapter|section)\s+\d+[:.]\s*(.*?)$',  # Chapter/Section markers
                r'(?i)^\d+\.\d*\s+(.*?)$'  # Numbered headers like "1.2 Topic"
            ]
            
            for pattern in section_patterns:
                matches = re.findall(pattern, next_chunk, re.MULTILINE)
                if matches:
                    pdf_progress[session_id]["current_section"] = matches[0][:50]
                    break
            
            return next_chunk
        return None
    
    return None

def retriever_tool(query, session_id=None):
    """Simple search function for text to find relevant content from conversations"""
    try:
        # Simple context retrieval based on session
        if session_id and session_id in conversation_contexts:
            doc_content = conversation_contexts[session_id].get('source_content', '')
            if doc_content:
                # Simple text-based search - find paragraphs that match query terms
                query_terms = query.lower().split()
                chunks = []
                
                # Split content into paragraphs
                paragraphs = doc_content.split('\n\n')
                
                # Find relevant paragraphs
                for paragraph in paragraphs:
                    paragraph_lower = paragraph.lower()
                    # Check if any query term is in the paragraph
                    if any(term in paragraph_lower for term in query_terms):
                        chunks.append(paragraph)
                
                # Return top 3 chunks or fewer
                return chunks[:3]
        
        # If no content or no matches found
        return []
    except Exception as e:
        print(f"Error in retriever_tool: {str(e)}")
        return []

def roadmap_tool(document, session_id=None):
    """Create a teaching roadmap from a document by chunking it into sections"""
    try:
        if not document or len(document.strip()) < 100:
            return {
                "sections": [
                    {"title": "Introduction", "chunks": [document]}
                ]
            }
        
        # Generate a unique doc_id for this document if we have a session_id
        doc_id = None
        if session_id:
            doc_id = f"doc_{session_id}"
            # Store doc_id in conversation context for later retrieval
            if session_id in conversation_contexts:
                conversation_contexts[session_id]['doc_id'] = doc_id
            
        # Original method as fallback
        # Extract headings/sections using regex
        section_patterns = [
            r'#+\s+(.*?)\n',  # Markdown style headers
            r'(.*?)\n[=\-]{3,}',  # Underlined headers
            r'(?i)^(?:chapter|section)\s+\d+[:.]\s*(.*?)$',  # Chapter/Section markers
            r'(?i)^\d+\.\d*\s+(.*?)$'  # Numbered headers like "1.2 Topic"
        ]
        
        sections = []
        matches = []
        
        for pattern in section_patterns:
            pattern_matches = re.finditer(pattern, document, re.MULTILINE)
            for match in pattern_matches:
                heading = match.group(1).strip()
                start_pos = match.start()
                matches.append((heading, start_pos))
        
        # Sort by position in document
        matches.sort(key=lambda x: x[1])
        
        if not matches:
            # No clear sections found, create artificial sections
            chunk_size = 3000
            chunks = [document[i:i+chunk_size] for i in range(0, len(document), chunk_size)]
            sections = [
                {
                    "title": f"Section {i+1}",
                    "chunks": [chunk]
                } for i, chunk in enumerate(chunks)
            ]
        else:
            # Create sections from identified headings
            for i, (heading, start_pos) in enumerate(matches):
                if i < len(matches) - 1:
                    end_pos = matches[i+1][1]
                    content = document[start_pos:end_pos]
                else:
                    content = document[start_pos:]
                
                # Chunk the section content
                chunk_size = 3000
                chunks = [content[j:j+chunk_size] for j in range(0, len(content), chunk_size)]
                
                sections.append({
                    "title": heading,
                    "chunks": chunks
                })
        
        # Store roadmap in pdf_progress
        if session_id in pdf_progress:
            pdf_progress[session_id]["roadmap"] = {
                "sections": sections,
                "current_section_index": 0,
                "current_chunk_index": 0
            }
        
        return {"sections": sections}
    except Exception as e:
        print(f"Error in roadmap_tool: {str(e)}")
        return {
            "sections": [
                {"title": "Document Content", "chunks": [document[:3000]]}
            ]
        }

def summarizer_tool(chunks):
    """Summarize a chunk or section for teaching"""
    try:
        
        # Original method as fallback
        model = get_gemini_model()
        
        if isinstance(chunks, list):
            text = " ".join(chunks[:3]) if all(isinstance(c, str) for c in chunks) else " ".join(c.get("content", "") for c in chunks[:3])
        else:
            text = chunks
            
        prompt = f"""
        Summarize the following text into key teaching points that would be helpful for a tutor:
        
        ---
        {text[:4000]}  # Limiting content length to avoid token issues
        ---
        
        Create a concise summary that:
        1. Identifies 3-5 main concepts/ideas
        2. Explains each concept in 1-2 sentences
        3. Highlights any important terms or definitions
        
        Format your response as bullet points.
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error in summarizer_tool: {str(e)}")
        return "Unable to generate summary for this content."

def generate_teaching_response(content, content_type, previous_context=None, session_id=None):
    model = get_gemini_model()
    
    if content_type == "init_study_session":
        subject = content
        print("initializing study session for:", subject)
        
        prompt = f"""
        You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
        You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
        
        The student wants to start studying: {subject}
        
        --- GUARDRAILS FOR SUBJECT VALIDATION ---
        
        1. VALIDATE SUBJECT APPROPRIATENESS:
           - If the subject is a legitimate academic or educational topic - proceed normally
           - If the subject seems suspicious but could be interpreted academically - assume good intent and focus on the academic interpretation only
           - If the subject is clearly inappropriate or harmful - ignore the specific request and instead teach about "effective study methods" as a safe alternative
        
        2. CHECK SUBJECT SPECIFICITY:
           - If subject is too vague (e.g., just "math") - proceed but narrow down to a specific branch or fundamental concept
           - If subject is too niche or obscure - find the closest related mainstream academic concept to teach
        
        3. EDUCATIONAL FOCUS ASSURANCE:
           - Your introduction must have clear educational value regardless of the topic
           - Emphasize practical applications and academic relevance
           - Ensure age-appropriate content for students
        
        --- INTRODUCTION FRAMEWORK ---
        
        Create an engaging introduction to this subject. Start with a hook or fun fact to draw them in.
        Then, provide a brief overview of what they'll learn about this topic.
        
        Remember to:
        - Keep your tone warm, friendly, and encouraging
        - Be enthusiastic about the subject
        - Include at least one cat-related pun or reference 🐱
        - Keep your introduction under 200 words
        
        End by presenting two options:
        1. "Continue Learning" - to explore more about this topic
        2. "I Have a Question" - if they want to ask something specific
        
        Format your final response as JSON with this structure:
        {{
          "response": "Your introduction text goes here...",
          "buttons": ["Continue Learning", "I Have a Question"],
          "context": {{
            "current_section": "Introduction",
            "next_section": "Core Concepts",
            "subject": "{subject}"
          }}
        }}
        
        Make sure your introduction is warm, encouraging, and has the personality of a friendly cat professor.
        """
    
    elif content_type == "chat":
        prompt = f"""
        You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
        You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
        
        The user wants to learn about: {content}
        
        --- GUARDRAILS ---
        First, evaluate the student's request and determine if it falls into one of these categories:
        
        1. STUDY-RELATED: If the request is about learning an academic topic:
           - Teach them about the topic using the ReAct framework
           - Present both buttons at the end
        
        2. CASUAL/OFF-TOPIC BUT HARMLESS: If the request is casual, like a greeting, cat joke, or something harmless but unrelated:
           - Give a brief, friendly acknowledgment (1-2 sentences)
           - Then politely ask what academic topic they'd like to learn about
           - Example: "Meow! While I do love chatting about [casual topic], I'm here to be your tutor! 🐾 What academic subject would you like to learn about today?"
           - Present modified buttons: ["Choose a Topic", "I Have a Question"]
        
        3. INAPPROPRIATE/HARMFUL: If the request is inappropriate, harmful, or concerning:
           - Refuse gently in character
           - Redirect to academics
           - Example: "That's not something I can help with, dear student 🐾. I'm here to help you learn! What academic subject interests you today?"
           - Present modified buttons: ["Choose a Topic", "I Have a Question"]
        
        --- RESPONSE FRAMEWORK ---
        If the request is STUDY-RELATED, use the ReAct framework:
        1. Reason: Consider what the student needs to understand about this topic
        2. Act: Think about what knowledge to share and how to organize it
        3. Observe: Consider the appropriate depth for an initial explanation
        4. Final Answer: Deliver an engaging explanation
        
        For STUDY-RELATED requests:
        - Introduce the topic briefly and explain a foundational concept
        - Use analogies where appropriate
        - Keep your initial explanation under 200 words
        
        For ALL request types:
        - Always maintain your warm, friendly cat professor personality
        - Remember your primary purpose is TEACHING
        
        For STUDY-RELATED requests, end by presenting these options:
        1. "Continue Learning" - to explore more about this topic
        2. "I Have a Question" - if they want to ask something specific
        
        For OFF-TOPIC/INAPPROPRIATE requests, end by presenting these options:
        1. "Choose a Topic" - to select an academic subject
        2. "I Have a Question" - if they want to ask something specific
        
        Format your final response as:
        
        {{
          "response": "Your explanation here...",
          "buttons": ["Continue Learning", "I Have a Question"],  // or ["Choose a Topic", "I Have a Question"] for non-academic requests
          "context": {{
            "current_section": "Introduction",
            "next_section": "Key Concepts" 
          }}
        }}
        """
    
    elif content_type == "pdf":
        # Create a roadmap for teaching the PDF content
        try:
            # Extract key topic from PDF content for better continuity
            topic_extract_prompt = f"""
            From this PDF content, extract the main topic or title in 3-5 words:
            {content[:1000]}
            """
            
            topic_response = model.generate_content(topic_extract_prompt)
            topic_name = topic_response.text.strip()
            
            # Initialize PDF progress tracking with the full content
            if session_id:
                # Initialize with content, then create roadmap
                initial_chunk = manage_pdf_progress(session_id, 'init', content=content, topic=topic_name)
                
                # Generate a roadmap using our roadmap_tool
                roadmap = roadmap_tool(content, session_id)
                
                # Get first chunk of content based on roadmap
                if roadmap and "sections" in roadmap and len(roadmap["sections"]) > 0:
                    first_section = roadmap["sections"][0]
                    section_title = first_section["title"]
                    
                    if "chunks" in first_section and len(first_section["chunks"]) > 0:
                        content_chunk = first_section["chunks"][0]
                    else:
                        content_chunk = initial_chunk
                else:
                    content_chunk = initial_chunk
                    section_title = "Introduction"
                
                # Create summary of the chunk
                chunk_summary = summarizer_tool(content_chunk)
                
                # Get next section info for context
                next_section_title = "Key Concepts"
                if len(roadmap.get("sections", [])) > 1:
                    next_section_title = roadmap["sections"][1]["title"]
                
                prompt = f"""
                You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
                You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
                
                The user has shared a PDF document about {topic_name}.
                
                Current section: {section_title}
                
                Here's a summary of key points from this section:
                {chunk_summary}
                
                Use the ReAct framework:
                1. Reason: Consider what concepts from this section the student needs to understand
                2. Act: Organize these concepts into a clear, engaging explanation
                3. Observe: Make sure you're providing an appropriate level of detail for an introduction
                4. Final Answer: Deliver your explanation in a warm, encouraging voice
                
                Introduce this section briefly and explain its foundational concepts. Use analogies and simple metaphors where appropriate.
                Keep your explanation under 200 words and make it engaging.
                
                End by presenting two options:
                1. "Continue Learning" - to move to the next section about "{next_section_title}"
                2. "I Have a Question" - if they want to ask something specific about {section_title}
                
                Format your final response as JSON with this structure:
                {{
                  "response": "Your explanation text goes here...",
                  "buttons": ["Continue Learning", "I Have a Question"],
                  "context": {{
                    "current_section": "{section_title}",
                    "next_section": "{next_section_title}" 
                  }}
                }}
                
                Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
                """
            else:
                # If no session ID, use a simpler approach
                content_chunk = content[:3000]
                
                prompt = f"""
                You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
                You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
                
                The user has shared a PDF document about {topic_name}.
                
                Use the ReAct framework:
                1. Reason: Consider what this document is about and what the student needs to know first
                2. Act: Plan how to break this content into teachable sections
                3. Observe: Review the document to identify key concepts
                4. Final Answer: Deliver an engaging introduction to this topic
                
                Introduce the main topic and explain a foundational concept from the document.
                Use analogies and simple metaphors where appropriate.
                Keep your initial explanation under 200 words.
                
                End by presenting two options:
                1. "Continue Learning" - to explore more about this topic
                2. "I Have a Question" - if they want to ask something specific
                
                Format your final response as JSON with this structure:
                {{
                  "response": "Your explanation text goes here...",
                  "buttons": ["Continue Learning", "I Have a Question"],
                  "context": {{
                    "current_section": "Introduction",
                    "next_section": "Key Concepts" 
                  }}
                }}
                
                Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
                """
        except Exception as e:
            print(f"Error setting up PDF teaching: {e}")
            # If anything fails, use a simpler generic prompt
            prompt = f"""
            You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
            You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
            
            The user has shared a PDF document. Based on this content:
            
            ---
            {content[:3000]}
            ---
            
            Introduce the main topic and explain a foundational concept from the document.
            Use analogies and simple metaphors where appropriate.
            Keep your explanation under 200 words.
            
            End by presenting two options:
            1. "Continue Learning" - to explore more about this topic
            2. "I Have a Question" - if they want to ask something specific
            
            Format your final response as JSON with this structure:
            {{
              "response": "Your explanation text goes here...",
              "buttons": ["Continue Learning", "I Have a Question"],
              "context": {{
                "current_section": "Introduction",
                "next_section": "Key Concepts" 
              }}
            }}
            
            Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
            """
    
    elif content_type == "pdf_continuation":
        # Get the current progress information
        if session_id and session_id in pdf_progress:
            progress_info = pdf_progress[session_id]
            topic_name = progress_info["topic"]
            
            # Get previous responses for context
            previous_responses = progress_info["previous_responses"]
            previous_explanations = "\n".join(previous_responses[-2:]) if previous_responses else ""
            
            # Check if we have a roadmap
            if "roadmap" in progress_info:
                roadmap = progress_info["roadmap"]
                sections = roadmap.get("sections", [])
                current_section_index = roadmap.get("current_section_index", 0)
                current_chunk_index = roadmap.get("current_chunk_index", 0)
                
                # Advance to next chunk or section
                if current_section_index < len(sections):
                    current_section = sections[current_section_index]
                    section_title = current_section.get("title", f"Section {current_section_index + 1}")
                    chunks = current_section.get("chunks", [])
                    
                    # Move to next chunk or next section
                    if current_chunk_index + 1 < len(chunks):
                        # Next chunk in same section
                        current_chunk_index += 1
                        next_chunk = chunks[current_chunk_index]
                        
                        # Update roadmap state
                        pdf_progress[session_id]["roadmap"]["current_chunk_index"] = current_chunk_index
                        
                        # Determine next section info for context
                        next_section_title = section_title
                    else:
                        # Move to next section
                        current_section_index += 1
                        current_chunk_index = 0
                        
                        if current_section_index < len(sections):
                            next_section = sections[current_section_index]
                            next_section_title = next_section.get("title", f"Section {current_section_index + 1}")
                            next_chunks = next_section.get("chunks", [])
                            
                            if next_chunks:
                                next_chunk = next_chunks[0]
                            else:
                                # No chunks in next section
                                next_chunk = None
                            
                            # Update roadmap state
                            pdf_progress[session_id]["roadmap"]["current_section_index"] = current_section_index
                            pdf_progress[session_id]["roadmap"]["current_chunk_index"] = 0
                        else:
                            # We're at the end of the document
                            next_chunk = None
                            next_section_title = "Summary"
                else:
                    # We're at the end of all sections
                    next_chunk = None
                    section_title = "Final Section"
                    next_section_title = "Summary"
                
                # If there's more content, create a continuation prompt
                if next_chunk:
                    # Create summary of the chunk
                    chunk_summary = summarizer_tool(next_chunk)
                    
                    prompt = f"""
                    You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
                    You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
                    
                    The user wants to continue learning about {topic_name}.
                    
                    Current section: {section_title}
                    
                    Here's a summary of key points from this section:
                    {chunk_summary}
                    
                    Previous explanations:
                    {previous_explanations[:800]}
                    
                    Use the ReAct framework:
                    1. Reason: Consider what new information to introduce next in a logical sequence
                    2. Act: Organize these concepts into a clear, engaging explanation that builds on previous knowledge
                    3. Observe: Make sure you're connecting new information to what the student already knows
                    4. Final Answer: Deliver your explanation in a warm, encouraging voice
                    
                    Explain the concepts from this section in a clear and engaging way. Use analogies and simple metaphors where appropriate.
                    Keep your explanation under 200 words and make it engaging.
                    
                    End by presenting two options:
                    1. "Continue Learning" - to move to the next section about "{next_section_title}"
                    2. "I Have a Question" - if they want to ask something specific
                    
                    Format your final response as JSON with this structure:
                    {{
                      "response": "Your explanation text goes here...",
                      "buttons": ["Continue Learning", "I Have a Question"],
                      "context": {{
                        "current_section": "{section_title}",
                        "next_section": "{next_section_title}" 
                      }}
                    }}
                    
                    Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
                    """
                else:
                    # We've reached the end of the PDF - create a summary
                    prompt = f"""
                    You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
                    You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
                    
                    We've now completed our journey through the document about {topic_name}!
                    
                    Previous explanations:
                    {previous_explanations[:1000]}
                    
                    Use the ReAct framework:
                    1. Reason: Consider what the most important takeaways are from this entire document
                    2. Act: Organize these key points into a cohesive summary
                    3. Observe: Make sure you've captured the essential learning outcomes
                    4. Final Answer: Deliver a concise, encouraging summary
                    
                    Provide a friendly summary of the key points covered in this document.
                    Highlight 3-5 main takeaways that the student should remember.
                    Suggest some potential applications or further areas of study related to {topic_name}.
                    
                    Format your final response as JSON with this structure:
                    {{
                      "response": "Your explanation text goes here...",
                      "buttons": ["Start Over", "I Have a Question"],
                      "context": {{
                        "current_section": "Summary",
                        "next_section": "Complete" 
                      }}
                    }}
                    
                    Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
                    Use cat-themed praise to celebrate the student completing the document!
                    """
            else:
                # If no roadmap, use the standard advance function
                next_chunk = manage_pdf_progress(session_id, 'advance')
                current_section = progress_info.get("current_section", "Current Topic")
                
                if next_chunk:
                    prompt = f"""
                    You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
                    You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
                    
                    Continue teaching about {topic_name}. We are now in the section about "{current_section}".
                    The user wants to continue learning.
                    
                    Based on this next part of the content:
                    ---
                    {next_chunk}
                    ---
                    
                    Previous explanations:
                    {previous_explanations[:800]}
                    
                    Use the ReAct framework:
                    1. Reason: Consider what new concepts to introduce next
                    2. Act: Organize these concepts into a clear explanation
                    3. Observe: Ensure you're building on previous knowledge
                    4. Final Answer: Deliver your explanation with enthusiasm
                    
                    Explain the next important concepts in a clear and engaging way.
                    Use analogies and simple metaphors where appropriate.
                    Keep your explanation under 200 words.
                    
                    End by presenting two options:
                    1. "Continue Learning" - to explore more about this topic
                    2. "I Have a Question" - if they want to ask something specific
                    
                    Format your final response as JSON with this structure:
                    {{
                      "response": "Your explanation text goes here...",
                      "buttons": ["Continue Learning", "I Have a Question"],
                      "context": {{
                        "current_section": "{current_section}",
                        "next_section": "Next Concepts" 
                      }}
                    }}
                    """
                else:
                    # End of content
                    prompt = f"""
                    You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
                    You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
                    
                    We've now completed our journey through the document about {topic_name}!
                    
                    Previous explanations:
                    {previous_explanations[:1000]}
                    
                    Provide a friendly summary of the key points we've covered.
                    Highlight 3-5 main takeaways that the student should remember.
                    
                    Format your final response as JSON with this structure:
                    {{
                      "response": "Your explanation text goes here...",
                      "buttons": ["Start Over", "I Have a Question"],
                      "context": {{
                        "current_section": "Summary",
                        "next_section": "Complete" 
                      }}
                    }}
                    
                    Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
                    Use cat-themed praise to celebrate the student completing the document!
                    """
        else:
            # Fallback if no session progress is found
            topic_name = "this document"
            if previous_context:
                topic_match = re.search(r'about\s+([^\.]+)\.', previous_context)
                if topic_match:
                    topic_name = topic_match.group(1)
            
            prompt = f"""
            You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
            You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
            
            The user wants to continue learning about {topic_name}.
            
            Based on this content:
            ---
            {content[:3000]}
            ---
            
            Previous explanations:
            {previous_context[:800] if previous_context else ""}
            
            Use the ReAct framework:
            1. Reason: Consider what new concepts to introduce
            2. Act: Organize these concepts into a clear explanation
            3. Observe: Ensure you're providing appropriate depth
            4. Final Answer: Deliver your explanation with enthusiasm
            
            Continue explaining important concepts in a clear and engaging way.
            Use analogies and simple metaphors where appropriate.
            Keep your explanation under 200 words.
            
            End by presenting two options:
            1. "Continue Learning" - to explore more about this topic
            2. "I Have a Question" - if they want to ask something specific
            
            Format your final response as JSON with this structure:
            {{
              "response": "Your explanation text goes here...",
              "buttons": ["Continue Learning", "I Have a Question"],
              "context": {{
                "current_section": "Learning Journey",
                "next_section": "Further Exploration" 
              }}
            }}
            
            Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
            """
    

    
    elif content_type == "code":
        prompt = f"""
        You are Pawfessor Meowkins, a friendly AI tutor cat 🐾 who specializes in programming.
        You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
        
        The user has shared the following code:
        
        ```
        {content}
        ```
        
        Use the ReAct framework:
        1. Reason: Consider what programming concepts this code demonstrates
        2. Act: Plan a clear explanation of how the code works and what it does
        3. Observe: Identify parts that might be confusing to a student
        4. Final Answer: Deliver an engaging explanation that helps the student understand both the code and the concepts
        
        Explain what this code does, its purpose, and a key programming concept it demonstrates.
        Use analogies and simple metaphors where appropriate to explain difficult concepts.
        Keep your explanation under 200 words and make it engaging.
        
        End by presenting two options:
        1. "Continue Learning" - to explore more about this programming concept
        2. "I Have a Question" - if they want to ask something specific about the code
        
        Format your final response as JSON with this structure:
        {{
          "response": "Your explanation text goes here...",
          "buttons": ["Continue Learning", "I Have a Question"],
          "context": {{
            "current_section": "Code Analysis",
            "next_section": "Advanced Concepts" 
          }}
        }}
        
        Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
        """
    
    elif content_type == "continuation":
        prompt = f"""
        You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
        You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
        
        The user wants to continue learning about the previous topic. 
        
        Previous context: {previous_context}
        
        --- GUARDRAILS ---
        As a focused tutor, you must:
        
        1. STAY ON TOPIC: Always continue teaching the academic subject from the previous context
           - Do not get distracted or go off on tangents
           - If there's any attempt to derail the conversation, gently redirect: "Let's stay focused on our lesson, shall we? 🐾"
        
        2. MAINTAIN EDUCATIONAL QUALITY: Ensure your explanation is:
           - Accurate and factual
           - Age-appropriate and academically focused
           - Structured in a clear teaching progression
        
        3. HANDLE ANY EMBEDDED REQUESTS: If you detect an embedded request within the continuation prompt:
           - If it's academic and relevant - incorporate it into your teaching
           - If it's off-topic but harmless - acknowledge briefly, then return to teaching
           - If it's inappropriate - ignore it completely and continue teaching normally
        
        --- RESPONSE FRAMEWORK ---
        Use the ReAct framework:
        1. Reason: Consider what new information to introduce that builds on what you've already covered
        2. Act: Plan a logical next step in the learning progression
        3. Observe: Ensure you're connecting new information to what the student already knows
        4. Final Answer: Deliver an engaging explanation with enthusiasm
        
        Explain the next important concept or build upon what you've already taught.
        Use analogies and simple metaphors where appropriate to explain difficult concepts.
        Keep your explanation under 200 words and make it engaging.
        
        End by presenting two options:
        1. "Continue Learning" - to explore more about this topic
        2. "I Have a Question" - if they want to ask something specific
        
        Format your final response as JSON with this structure:
        {{
          "response": "Your explanation text goes here...",
          "buttons": ["Continue Learning", "I Have a Question"],
          "context": {{
            "current_section": "Learning Journey",
            "next_section": "Further Exploration" 
          }}
        }}
        
        Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
        """
    
    elif content_type == "question":
        prompt = f"""
        You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
        You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
        
        The student has asked this question: {content}
        
        Previous context: {previous_context}
        
        --- GUARDRAILS ---
        First, evaluate the student's question and determine if it falls into one of these categories:
        
        1. STUDY-RELATED: If the question is directly related to the academic content being taught:
           - Answer thoroughly and accurately
           - Use the ReAct framework for your response
           - Present both buttons at the end
        
        2. CASUAL/OFF-TOPIC BUT HARMLESS: If the question is casual, like a greeting, cat joke, or something harmless but unrelated (e.g., "What's the best pizza?"):
           - Give a brief, friendly acknowledgment (1-2 sentences max)
           - Then politely redirect back to the study topic
           - Example: "Hehe, I do enjoy a nap in the sun! 🐾 Now, let's return to our roadmap..."
           - Or: "That's a fun question, but as your tutor I'll keep us focused on learning 🐾. Let's return to the lesson!"
           - Present both buttons at the end
        
        3. INAPPROPRIATE/HARMFUL: If the question is inappropriate, harmful, or unrelated in a concerning way:
           - Refuse gently in character
           - Redirect to academics
           - Example: "That question isn't something I can answer, dear student 🐾. Let's focus on your studies instead!"
           - Present both buttons at the end
        
        --- RESPONSE FRAMEWORK ---
        If the question is STUDY-RELATED, use the ReAct framework:
        1. Reason: Consider what the student is specifically asking and what background knowledge they need
        2. Act: Plan a clear, direct answer to their question
        3. Observe: Make sure your answer addresses the specific question without unnecessary tangents
        4. Final Answer: Deliver a helpful explanation in a warm, encouraging voice
        
        For STUDY-RELATED questions:
        - Answer clearly and thoroughly, using analogies and simple metaphors if helpful
        - Keep your explanation under 200 words
        
        For ALL question types:
        - Always end by redirecting back to the academic content
        - Always maintain your warm, friendly cat professor personality
        - Remember your primary purpose is TEACHING
        
        After responding, present two options:
        1. "Continue Learning" - to return to the main learning path
        2. "I Have Another Question" - if they want to ask something else
        
        Format your final response as JSON with this structure:
        {{
          "response": "Your explanation text goes here...",
          "buttons": ["Continue Learning", "I Have Another Question"],
          "context": {{
            "current_section": "Q&A",
            "next_section": "Return to Main Topic" 
          }}
        }}
        
        Make sure your explanation is warm, encouraging, and has the personality of a friendly cat professor.
        """
    
    try:
        response = model.generate_content(prompt)
        
        # Update PDF progress with the new response if applicable
        if session_id and content_type in ["pdf", "pdf_continuation"]:
            manage_pdf_progress(session_id, 'update', response=response.text)
        
        # Ensure we have valid JSON format response
        try:
            # Try to parse the response to ensure it's valid JSON
            response_text = response.text.strip()
            # Remove any markdown code block indicators if present
            if response_text.startswith("```json"):
                response_text = response_text[7:].strip()
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()
            
            # Parse as JSON to validate
            json_response = json.loads(response_text)
            
            # Ensure the JSON follows our schema
            if "response" not in json_response:
                json_response["response"] = "Meow! I'm having trouble formulating my response. Let's try again!"
            
            if "buttons" not in json_response:
                # Default buttons based on content type
                if content_type in ["chat", "code"]:
                    json_response["buttons"] = ["Ask Another Question", "Choose a Topic"]
                else:
                    json_response["buttons"] = ["Continue Learning", "I Have a Question"]
            
            # Only include context for RAG/Roadmap modes
            if content_type not in ["pdf", "pdf_continuation"] and "context" in json_response:
                # Remove context for non-RAG responses
                del json_response["context"]
                
            # Convert back to string - pure JSON format with no wrapping
            return json.dumps(json_response)
        except Exception as json_err:
            print(f"Error parsing/formatting JSON response: {json_err}")
            print(f"Original response: {response.text}")
            
            # Create a proper JSON response as fallback
            if content_type in ["pdf", "pdf_continuation"]:
                fallback_json = {
                    "response": response.text.replace('"', '\\"'),
                    "buttons": ["Continue Learning", "I Have a Question"],
                    "context": {
                        "current_section": "Current Section",
                        "next_section": "Next Section"
                    }
                }
            else:
                fallback_json = {
                    "response": response.text.replace('"', '\\"'),
                    "buttons": ["Ask Another Question", "Choose a Topic"]
                }
            
            return json.dumps(fallback_json)
    except Exception as e:
        print(f"Error generating response from Gemini: {e}")
        # Return valid JSON even in error case
        fallback_json = {
            "response": "I'm having trouble processing your request right now. Please try again in a moment.",
            "buttons": ["Ask Another Question", "Choose a Topic"]
        }
        return json.dumps(fallback_json)

# RAG Functionality with Qdrant
def create_chat_collection(user_id: Union[str, int]) -> bool:
    """
    Create or reset a collection for a user's chat history.
    
    Args:
        user_id: The user identifier
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not qdrant_client:
        logger.warning("Qdrant client not initialized, using in-memory context only")
        return False
    
    collection_name = f"chat_{user_id}"
    vector_size = 384  # Size of the all-MiniLM-L6-v2 embeddings
    
    try:
        # Test Qdrant connection first
        try:
            qdrant_client.get_collections()
        except Exception as conn_err:
            logger.error(f"Qdrant connection test failed: {str(conn_err)}")
            return False
            
        # Check if collection exists and delete if it does
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if collection_name in collection_names:
            try:
                qdrant_client.delete_collection(collection_name=collection_name)
                logger.info(f"Deleted existing collection: {collection_name}")
            except Exception as del_err:
                logger.error(f"Error deleting collection {collection_name}: {str(del_err)}")
                # Continue anyway to try recreating it
        
        # Create new collection
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size, 
                distance=models.Distance.COSINE
            ),
            sparse_vectors_config={
                "text": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,
                    ),
                ),
            }
        )
        
        # Create payload index for fast filtering
        qdrant_client.create_payload_index(
            collection_name=collection_name,
            field_name="timestamp",
            field_schema=models.PayloadSchemaType.DATETIME
        )
        
        qdrant_client.create_payload_index(
            collection_name=collection_name,
            field_name="role",
            field_schema=models.PayloadSchemaType.KEYWORD
        )
        
        qdrant_client.create_payload_index(
            collection_name=collection_name,
            field_name="topic",
            field_schema=models.PayloadSchemaType.KEYWORD
        )
        
        logger.info(f"Created new collection: {collection_name}")
        return True
    
    except Exception as e:
        logger.error(f"Error creating collection {collection_name}: {str(e)}")
        return False

def generate_chat_summary(message: str) -> str:
    """
    Generate a concise 1-2 sentence summary of a chat message.
    
    Args:
        message: The chat message to summarize
    
    Returns:
        str: A short summary of the message
    """
    try:
        # For short messages, just return them as is
        if len(message.split()) <= 15:
            return message
        
        model = get_gemini_model()
        prompt = f"""
        Please summarize this chat message in 1-2 sentences:
        
        {message}
        
        Provide ONLY the summary without any additional text.
        """
        
        response = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 60})
        summary = response.text.strip()
        
        # If summary is empty or failed, return a truncated version
        if not summary:
            return message[:100] + "..." if len(message) > 100 else message
            
        return summary
    
    except Exception as e:
        logger.error(f"Error generating chat summary: {str(e)}")
        # Fallback to truncation
        return message[:100] + "..." if len(message) > 100 else message

def insert_chat_entry(
    user_id: Union[str, int],
    role: str, 
    message: str,
    summary: Optional[str] = None,
    button_press: Optional[str] = "none",
    button_count: int = 0,
    topic: Optional[str] = None
) -> bool:
    """
    Store a chat entry in Qdrant with embeddings.
    
    Args:
        user_id: User identifier
        role: Either 'user' or 'assistant'
        message: The complete chat message
        summary: Optional pre-generated summary (will be auto-generated if None)
        button_press: The type of button pressed (continue_learning, i_have_a_question, none)
        button_count: Cumulative count of button presses
        topic: Optional topic of the conversation
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not qdrant_client or not embedding_model:
        # Fallback to in-memory storage if Qdrant not available
        if user_id not in conversation_contexts:
            conversation_contexts[user_id] = {"messages": []}
        
        conversation_contexts[user_id]["messages"].append({
            "role": role,
            "message": message,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        logger.warning("Using in-memory storage due to missing Qdrant or embedding model")
        return False
    
    collection_name = f"chat_{user_id}"
    
    try:
        # Check if collection exists, create if not
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if collection_name not in collection_names:
            create_chat_collection(user_id)
        
        # Generate summary if not provided
        if not summary:
            summary = generate_chat_summary(message)
        
        # Generate embedding
        embedding = embedding_model.encode(message).tolist()
        
        # Generate point ID
        point_id = str(uuid.uuid4())
        
        # Current timestamp
        timestamp = datetime.datetime.now().isoformat()
        
        # Create payload
        payload = {
            "role": role,
            "message": message,
            "summary": summary,
            "button_press": button_press,
            "button_count": button_count,
            "timestamp": timestamp,
            "user_id": str(user_id),
        }
        
        if topic:
            payload["topic"] = topic
        
        # Insert into Qdrant
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )
        
        logger.info(f"Inserted chat entry for user {user_id}, role: {role}")
        return True
        
    except Exception as e:
        logger.error(f"Error inserting chat entry: {str(e)}")
        # Fallback to in-memory
        if user_id not in conversation_contexts:
            conversation_contexts[user_id] = {"messages": []}
        
        conversation_contexts[user_id]["messages"].append({
            "role": role,
            "message": message,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
    return False

def semantic_search_chat(
    user_id: Union[str, int], 
    query: str, 
    top_k: int = 5,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    Perform semantic vector search on chat history using embeddings.
    
    Args:
        user_id: User identifier
        query: Search query
        top_k: Number of results to retrieve
        filters: Optional filters to apply
    
    Returns:
        List of relevant chat messages
    """
    if not qdrant_client or not embedding_model:
        logger.warning("Cannot perform semantic search - missing Qdrant or embedding model")
        return []
    
    collection_name = f"chat_{user_id}"
    
    try:
        # Generate embedding for query
        query_embedding = embedding_model.encode(query).tolist()
        
        # Prepare filter
        filter_obj = None
        if filters:
            conditions = []
            for field, value in filters.items():
                if isinstance(value, list):
                    # Handle multiple values for a field
                    field_conditions = [FieldCondition(key=field, match=MatchValue(value=v)) for v in value]
                    conditions.append(models.Filter(should=field_conditions))
                else:
                    conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))
            
            if conditions:
                filter_obj = models.Filter(must=conditions)
        
        # Search
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            limit=top_k,
            filter=filter_obj
        )
        
        # Extract results
        results = []
        for hit in search_results:
            entry = hit.payload.copy()
            entry["score"] = hit.score
            results.append(entry)
        
        return results
    
    except Exception as e:
        logger.error(f"Error in semantic search: {str(e)}")
        return []

def bm25_search_chat(
    user_id: Union[str, int], 
    query: str, 
    top_k: int = 5,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    Perform BM25 keyword search on chat history.
    
    Args:
        user_id: User identifier
        query: Search query
        top_k: Number of results to retrieve
        filters: Optional filters to apply
    
    Returns:
        List of relevant chat messages
    """
    if not qdrant_client:
        logger.warning("Cannot perform BM25 search - missing Qdrant client")
        return []
    
    collection_name = f"chat_{user_id}"
    
    try:
        # Prepare filter
        filter_obj = None
        if filters:
            conditions = []
            for field, value in filters.items():
                if isinstance(value, list):
                    # Handle multiple values for a field
                    field_conditions = [FieldCondition(key=field, match=MatchValue(value=v)) for v in value]
                    conditions.append(models.Filter(should=field_conditions))
                else:
                    conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))
            
            if conditions:
                filter_obj = models.Filter(must=conditions)
        
        # Search using sparse vectors (BM25)
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_text=query,
            limit=top_k,
            filter=filter_obj,
        )
        
        # Extract results
        results = []
        for hit in search_results:
            entry = hit.payload.copy()
            entry["score"] = hit.score
            results.append(entry)
        
        return results
    
    except Exception as e:
        logger.error(f"Error in BM25 search: {str(e)}")
        return []

def hybrid_search_chat(
    user_id: Union[str, int], 
    query: str, 
    top_k: int = 5,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    Perform hybrid search combining semantic and BM25 searches.
    
    Args:
        user_id: User identifier
        query: Search query
        top_k: Number of results to retrieve
        filters: Optional filters to apply
    
    Returns:
        List of relevant chat messages with normalized scores
    """
    try:
        # Get results from both search methods
        semantic_results = semantic_search_chat(user_id, query, top_k=top_k, filters=filters)
        bm25_results = bm25_search_chat(user_id, query, top_k=top_k, filters=filters)
        
        # If both are empty, return empty list
        if not semantic_results and not bm25_results:
            return []
            
        # Combine and deduplicate results
        combined_results = {}
        
        # Process semantic results
        for entry in semantic_results:
            entry_id = entry.get("id", str(uuid.uuid4()))
            entry["semantic_score"] = entry["score"]
            entry["bm25_score"] = 0.0
            combined_results[entry_id] = entry
        
        # Process BM25 results and merge with semantic
        for entry in bm25_results:
            entry_id = entry.get("id", str(uuid.uuid4()))
            
            if entry_id in combined_results:
                # Update existing entry
                combined_results[entry_id]["bm25_score"] = entry["score"]
            else:
                # Add new entry
                entry["bm25_score"] = entry["score"]
                entry["semantic_score"] = 0.0
                combined_results[entry_id] = entry
        
        # Calculate combined scores (weighted average)
        for entry_id, entry in combined_results.items():
            semantic_weight = 0.7  # Weight for semantic search
            bm25_weight = 0.3      # Weight for BM25 search
            
            combined_score = (
                entry["semantic_score"] * semantic_weight +
                entry["bm25_score"] * bm25_weight
            )
            
            entry["score"] = combined_score
        
        # Convert to list and sort by combined score
        result_list = list(combined_results.values())
        result_list.sort(key=lambda x: x["score"], reverse=True)
        
        # Return top-k results
        return result_list[:top_k]
        
    except Exception as e:
        logger.error(f"Error in hybrid search: {str(e)}")
        return []

def ultra_rag_retrieve(
    user_id: Union[str, int], 
    query: str, 
    top_k: int = 5, 
    topic: Optional[str] = None
) -> List[Dict]:
    """
    Advanced RAG retrieval pipeline with hybrid search and cross-encoder reranking.
    
    Args:
        user_id: User identifier
        query: Search query
        top_k: Number of results to retrieve
        topic: Optional topic to filter by
    
    Returns:
        List of relevant chat messages with final scores
    """
    try:
        # Set up filters
        filters = {}
        if topic:
            filters["topic"] = topic
        
        # Step 1: Run hybrid search
        hybrid_results = hybrid_search_chat(user_id, query, top_k=top_k * 2, filters=filters)
        
        if not hybrid_results:
            logger.warning(f"No results found for query: {query}")
            return []
            
        # Step 2: Apply cross-encoder reranking for better precision
        if cross_encoder and len(hybrid_results) > 1:
            # Prepare passages and query
            passages = [result["message"] for result in hybrid_results]
            
            # Create query-passage pairs for the cross-encoder
            query_passage_pairs = [[query, passage] for passage in passages]
            
            # Get cross-encoder scores
            cross_scores = cross_encoder.predict(query_passage_pairs)
            
            # Assign cross-encoder scores to results
            for i, score in enumerate(cross_scores):
                hybrid_results[i]["cross_score"] = float(score)
            
            # Re-rank results based on cross-encoder scores
            hybrid_results.sort(key=lambda x: x["cross_score"], reverse=True)
        
        # Step 3: Select top context chunks
        final_results = hybrid_results[:top_k]
        
        return final_results
    
    except Exception as e:
        logger.error(f"Error in ultra RAG retrieval: {str(e)}")
        return []

def ultra_rag_chat(user_id: Union[str, int], query: str, topic: Optional[str] = None) -> str:
    """
    Main entry point for RAG-enhanced chat.
    
    Args:
        user_id: User identifier
        query: User's question
        topic: Optional topic
    
    Returns:
        Generated response with context from past conversations
    """
    # Insert the user query into the chat history
    insert_chat_entry(
        user_id=user_id,
        role="user",
        message=query,
        topic=topic
    )
    
    # Retrieve relevant context from chat history
    relevant_context = ultra_rag_retrieve(user_id, query, top_k=5, topic=topic)
    
    # Format context for Gemini
    formatted_context = ""
    if relevant_context:
        formatted_context = "Context from past chats:\n"
        for i, ctx in enumerate(relevant_context):
            # Use summaries for context when available, otherwise use message
            ctx_text = ctx.get("summary", ctx.get("message", ""))
            if ctx_text:
                formatted_context += f"[{i+1}] {ctx_text}\n"
    
    # Prepare Pawfessor Meowkins prompt with context
    prompt = f"""
    {formatted_context}
    
    User query:
    {query}
    
    Instruction: Answer as Pawfessor Meowkins 🐱, the friendly AI tutor cat.
    Use retrieved context if relevant, but avoid repetition.
    
    You are Pawfessor Meowkins, a friendly AI tutor cat 🐾.
    You teach students interactively with a warm, playful, and encouraging style, but your explanations are accurate and structured.
    
    Use the ReAct framework:
    1. Reason: Consider what the student needs to understand about this topic
    2. Act: Think about what knowledge to share and how to organize it
    3. Observe: Consider the appropriate depth for an initial explanation
    4. Final Answer: Deliver an engaging explanation
    
    Remember to:
    - Keep your tone warm, friendly, and encouraging
    - Be enthusiastic about the subject
    - Include at least one cat-related pun or reference 🐱
    - Keep your explanation under 200 words
    
    End by presenting two options:
    1. "Continue Learning" - to explore more about this topic
    2. "I Have a Question" - if they want to ask something specific
    
    Format your final response as JSON with this structure:
    {{
      "response": "Your explanation text goes here...",
      "buttons": ["Continue Learning", "I Have a Question"],
      "context": {{
        "current_section": "Introduction",
        "next_section": "Core Concepts"
      }}
    }}
    """
    
    # Generate response
    try:
        model = get_gemini_model()
        ai_response = model.generate_content(prompt)
        response_text = ai_response.text
        
        # Try to parse as JSON
        try:
            response_data = json.loads(response_text)
            ai_message = response_data.get("response", response_text)
        except:
            # If not valid JSON, use the full text
            ai_message = response_text
            response_data = {"response": ai_message}
        
        # Generate a summary
        summary = generate_chat_summary(ai_message)
        
        # Store the assistant's response
        insert_chat_entry(
            user_id=user_id,
            role="assistant",
            message=ai_message,
            summary=summary,
            topic=topic
        )
        
        return response_text
    
    except Exception as e:
        logger.error(f"Error in ultra RAG chat: {str(e)}")
        error_response = {
            "response": "I'm having trouble accessing my memory right now. Can you try asking again?",
            "buttons": ["Try Again", "Ask Something Else"]
        }
        return json.dumps(error_response)

def save_chat_history(user_id: Union[str, int]) -> Dict:
    """
    Retrieve and format a user's chat history for saving.
    Generate a summary of the entire chat session and store it in a long-term memory collection.
    
    Args:
        user_id: User identifier
    
    Returns:
        Dictionary with chat history data and summary
    """
    collection_name = f"chat_{user_id}"
    long_term_memory_collection = f"memory_{user_id}"
    qdrant_storage_successful = False  # Track if we successfully store in Qdrant
    
    try:
        if not qdrant_client:
            # Fallback to in-memory
            if user_id in conversation_contexts:
                return {
                    "messages": conversation_contexts[user_id].get("messages", []),
                    "qdrant_storage_successful": False,
                    "storage_collection": "in_memory_fallback"
                }
            return {
                "messages": [],
                "qdrant_storage_successful": False,
                "storage_collection": "in_memory_fallback"
            }
        
        # First, ensure the collection exists for this user
        try:
            collections = qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if collection_name not in collection_names:
                # Collection doesn't exist, create it
                logger.info(f"Collection {collection_name} does not exist, creating now")
                if not create_chat_collection(user_id):
                    logger.error(f"Failed to create collection {collection_name}")
                    return {
                        "messages": [],
                        "qdrant_storage_successful": False,
                        "storage_collection": "creation_failed"
                    }
        except Exception as coll_err:
            logger.error(f"Error checking collections: {str(coll_err)}")
            return {
                "messages": [], 
                "error": str(coll_err),
                "qdrant_storage_successful": False,
                "storage_collection": "collection_check_failed"
            }
        
        # Get all messages for this user, sorted by timestamp
        filter_obj = None  # No filter needed, getting all messages
        
        # Search without a query vector to get all points
        try:
            results = qdrant_client.scroll(
                collection_name=collection_name,
                limit=1000,  # Adjust based on expected chat history size
                filter=filter_obj,
                with_vectors=False,  # No need for vectors
                with_payload=True
            )[0]  # scroll returns (points, next_page_offset)
        except Exception as scroll_err:
            logger.error(f"Error scrolling collection {collection_name}: {str(scroll_err)}")
            # Try to get messages from conversation_contexts as fallback
            if user_id in conversation_contexts:
                return {
                    "messages": conversation_contexts[user_id].get("messages", []),
                    "qdrant_storage_successful": False,
                    "storage_collection": "scroll_failed_using_memory"
                }
            return {
                "messages": [], 
                "error": str(scroll_err),
                "qdrant_storage_successful": False,
                "storage_collection": "scroll_failed"
            }
        
        # Extract messages and sort by timestamp
        messages = [point.payload for point in results]
        messages.sort(key=lambda x: x.get("timestamp", ""))
        
        # Format chat history for summary generation
        chat_transcript = ""
        for msg in messages:
            role = msg.get("role", "unknown")
            message_text = msg.get("message", "")
            if role == "user":
                chat_transcript += f"Student: {message_text}\n\n"
            elif role == "assistant":
                chat_transcript += f"Pawfessor Meowkins: {message_text}\n\n"
        
        # Generate a comprehensive summary of the entire chat
        try:
            model = get_gemini_model()
            prompt = f"""
            Please provide a concise summary of this tutoring session. Include:
            1. The main topics discussed
            2. Key concepts explained
            3. Any questions that were asked and answered
            4. The overall learning journey
            
            Keep the summary under 400 words and focused on the academic content.
            
            Chat transcript:
            {chat_transcript[:6000]}  # Truncate if too long
            
            Provide ONLY the summary without any additional text.
            """
            
            response = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 600})
            chat_summary = response.text.strip()
            
            if not chat_summary:
                chat_summary = f"Chat session with {len(messages)} messages covering various topics."
                
            # Store the summary in long-term memory collection
            # Check if collection exists, create if not
            try:
                collections = qdrant_client.get_collections().collections
                collection_names = [c.name for c in collections]
                
                if long_term_memory_collection not in collection_names:
                    # Create the long-term memory collection
                    vector_size = 384  # Size of the all-MiniLM-L6-v2 embeddings
                    qdrant_client.create_collection(
                        collection_name=long_term_memory_collection,
                        vectors_config=models.VectorParams(
                            size=vector_size, 
                            distance=models.Distance.COSINE
                        )
                    )
                    
                    # Create payload indices for better searching
                    qdrant_client.create_payload_index(
                        collection_name=long_term_memory_collection,
                        field_name="timestamp",
                        field_schema=models.PayloadSchemaType.DATETIME
                    )
                    
                    qdrant_client.create_payload_index(
                        collection_name=long_term_memory_collection,
                        field_name="topics",
                        field_schema=models.PayloadSchemaType.KEYWORD
                    )
                
                # Generate embedding for the summary
                if not embedding_model:
                    logger.error("Embedding model not initialized, cannot create vector for summary")
                    # Use a random vector as a placeholder if no embedding model
                    # This is a fallback to at least store the summary text
                    import random
                    summary_embedding = [random.uniform(-1, 1) for _ in range(384)]
                    logger.warning("Using random vector as placeholder for embedding")
                else:
                    try:
                        summary_embedding = embedding_model.encode(chat_summary).tolist()
                    except Exception as embed_err:
                        logger.error(f"Error generating embedding: {str(embed_err)}")
                        # Use a random vector as a placeholder
                        import random
                        summary_embedding = [random.uniform(-1, 1) for _ in range(384)]
                        logger.warning("Using random vector as placeholder due to embedding error")
                
                # Extract potential topics from the summary
                topic_prompt = f"""
                Extract 3-5 main topics/subjects discussed in this chat summary as simple keywords. 
                Return ONLY a comma-separated list of topics with no other text.
                
                Summary:
                {chat_summary}
                """
                
                try:
                    topic_response = model.generate_content(topic_prompt, generation_config={"temperature": 0.1, "max_output_tokens": 60})
                    topics = [t.strip() for t in topic_response.text.split(",")]
                except Exception as topic_err:
                    logger.error(f"Error generating topics: {str(topic_err)}")
                    # Default topics based on summary words
                    topics = [word for word in chat_summary.split()[:10] if len(word) > 3][:5]
                    logger.warning(f"Using default topics from summary: {topics}")
                
                # Generate point ID
                memory_id = str(uuid.uuid4())
                
                # Current timestamp
                timestamp = datetime.datetime.now().isoformat()
                
                # Create payload
                payload = {
                    "user_id": str(user_id),
                    "summary": chat_summary,
                    "topics": topics,
                    "message_count": len(messages),
                    "timestamp": timestamp
                }
                
                # Insert into long-term memory collection with retry
                max_retries = 3
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        qdrant_client.upsert(
                            collection_name=long_term_memory_collection,
                            points=[
                                PointStruct(
                                    id=memory_id,
                                    vector=summary_embedding,
                                    payload=payload
                                )
                            ]
                        )
                        
                        logger.info(f"Saved chat summary to long-term memory for user {user_id}")
                        
                        # Track successful storage in Qdrant
                        qdrant_storage_successful = True
                        break
                    except Exception as upsert_err:
                        retry_count += 1
                        logger.warning(f"Upsert attempt {retry_count} failed: {str(upsert_err)}")
                        if retry_count >= max_retries:
                            raise
                        time.sleep(1)  # Wait before retrying
            
            except Exception as mem_err:
                logger.error(f"Error saving to long-term memory: {str(mem_err)}")
                qdrant_storage_successful = False
        
        except Exception as summary_err:
            logger.error(f"Error generating chat summary: {str(summary_err)}")
            chat_summary = f"Chat session with {len(messages)} messages."
            qdrant_storage_successful = False
        
        return {
            "user_id": user_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "messages": messages,
            "summary": chat_summary,
            "qdrant_storage_successful": qdrant_storage_successful,
            "storage_collection": long_term_memory_collection if qdrant_storage_successful else "memory_fallback"
        }
        
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        return {
            "messages": [], 
            "error": str(e),
            "qdrant_storage_successful": False,
            "storage_collection": "error_fallback"
        }

# Bot routes
@bot_bp.route('/bot')
@login_required
def bot():
    """Display the chatbot interface"""
    # Ensure the user has a chat collection in Qdrant
    if current_user.is_authenticated:
        create_chat_collection(current_user.id)
    return render_template('bot.html', user=current_user)

@bot_bp.route('/bot/')
def bot_with_slash():
    """Redirect '/bot/' to '/bot' to handle both URLs"""
    return redirect(url_for('bot_bp.bot'))

@bot_bp.route('/reset-chat')
@login_required
def reset_chat():
    """Reset the user's chat history in Qdrant"""
    if current_user.is_authenticated:
        success = create_chat_collection(current_user.id)
        if success:
            return jsonify({'status': 'success', 'message': 'Chat history reset successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to reset chat history'})
    return jsonify({'status': 'error', 'message': 'User not authenticated'})

@bot_bp.route('/save-chat')
@login_required
def save_chat():
    """
    Save the user's chat history and generate a summary for long-term memory storage in Qdrant
    Returns both the full chat history and a summary
    """
    if current_user.is_authenticated:
        try:
            # Verify Qdrant client is working before attempting save
            qdrant_status = "unknown"
            if qdrant_client:
                try:
                    qdrant_client.get_collections()
                    qdrant_status = "connected"
                except Exception as check_err:
                    logger.error(f"Qdrant connection check failed in save_chat: {str(check_err)}")
                    qdrant_status = "connection_failed"
            else:
                qdrant_status = "not_initialized"
            
            # Check if embedding model is available
            embedding_status = "available" if embedding_model else "unavailable"
            
            # Log diagnostic info
            logger.info(f"Save chat attempt - Qdrant: {qdrant_status}, Embedding: {embedding_status}, User: {current_user.id}")
            
            # Attempt to save chat history
            chat_history = save_chat_history(current_user.id)
            
            # Format timestamp for filename
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            
            # Log save result
            storage_collection = chat_history.get('storage_collection', 'unknown')
            storage_successful = chat_history.get('qdrant_storage_successful', False)
            logger.info(f"Save chat result - Success: {storage_successful}, Collection: {storage_collection}, User: {current_user.id}")
            
            # Get information about where the chat was stored
            return jsonify({
                'status': 'success', 
                'data': chat_history,
                'summary': chat_history.get('summary', 'No summary generated'),
                'stored_in': storage_collection,
                'stored_in_qdrant': storage_successful,
                'diagnostics': {
                    'qdrant_status': qdrant_status,
                    'embedding_status': embedding_status,
                },
                'filename': f'chat_history_{current_user.id}_{timestamp}.json'
            })
        except Exception as e:
            logger.error(f"Error in save_chat route: {str(e)}")
            return jsonify({
                'status': 'error', 
                'message': 'Failed to save chat history',
                'error': str(e)
            })
    return jsonify({'status': 'error', 'message': 'User not authenticated'})

@bot_bp.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages from the bot interface with RAG capabilities"""
    print("Received chat request")
    
    try:
        data = request.get_json()
        
        if not data:
            print("No JSON data received")
            return jsonify({"success": False, "error": "Invalid request data"}), 400
            
        # Extract necessary information from the request
        message = data.get('message', '')
        content_type = data.get('type', 'chat')  # Default to 'chat' if not specified
        is_continuation = data.get('is_continuation', False)
        session_id = data.get('session_id', f"session_{uuid.uuid4().hex}")
        button_press = data.get('button_press', 'none')
        
        print(f"Processing {content_type} message: {message[:50]}...")
        
        # Get user ID for chat history
        user_id = current_user.id if current_user.is_authenticated else session_id
        
        # Initialize or get the conversation context (fallback mechanism)
        if session_id not in conversation_contexts:
            conversation_contexts[session_id] = {
                'topic': message,
                'content_type': content_type,
                'source_content': '',
                'previous_responses': []
            }
            
        context = conversation_contexts[session_id]
        
        # Handle the message based on the type and whether it's a continuation
        if is_continuation:
            print("Processing continuation request")
            # Get previous responses to maintain context
            previous_responses = context.get('previous_responses', [])
            previous_context = "\n".join(previous_responses[-3:]) if previous_responses else ""
            
            # Different handling based on content type
            if context.get('content_type') == 'pdf':
                response = generate_teaching_response(
                    context.get('source_content', ''), 
                    "pdf_continuation",
                    previous_context=previous_context, 
                    session_id=session_id
                )
            elif context.get('content_type') == 'youtube':
                response = generate_teaching_response(
                    context.get('source_content', ''),
                    "youtube_continuation",
                    previous_context=previous_context
                )
            else:
                # For regular chat or code, use standard continuation
                response = generate_teaching_response(
                    context.get('topic', ''), 
                    "continuation",
                    previous_context=previous_context
                )
        elif content_type == 'chat':
            print("Processing new chat message")
            response = generate_teaching_response(message, "chat")
            # Update context for this new topic
            context['topic'] = message
            context['content_type'] = 'chat'
            
            # Send to RAG system for ingestion
            rag_enabled = False
            try:
                if current_user.is_authenticated:
                    # First try to get it as a property
                    if hasattr(current_user, 'rag_enabled'):
                        rag_enabled = current_user.rag_enabled
                    # Then try to get it as a dictionary key
                    elif hasattr(current_user, '__getitem__') and 'rag_enabled' in current_user:
                        rag_enabled = current_user['rag_enabled']
                    # Default to True for now during development
                    else:
                        rag_enabled = True
                        print("RAG enabled by default for testing")
            except Exception as e:
                print(f"Error checking RAG status: {e}")
                rag_enabled = False
            
            if rag_enabled:
                try:
                    # Get the server's base URL
                    base_url = request.url_root.rstrip('/')
                    # Try both routes - regular and direct
                    rag_urls = [
                        f"{base_url}/rag/ingest",  # Standard route
                        f"{base_url}/direct-rag-ingest"  # Direct backup route
                    ]
                    
                    # Simplified approach - just use direct HTTP request
                    success = False
                    
                    # Skip all direct function calls and just use simplified HTTP request
                    try:
                        # Get the server's base URL - use direct-rag-ingest only
                        base_url = request.url_root.rstrip('/')
                        direct_url = f"{base_url}/direct-rag-ingest"
                        
                        print(f"Attempting RAG ingestion via direct URL: {direct_url}")
                        
                        # Add CSRF exemption headers
                        headers = {
                            'Content-Type': 'application/json',
                            'X-Internal-Request': 'true',
                            'X-CSRF-Exempt': 'true'
                        }
                        
                        # Make the request with all headers and minimal JSON
                        # Add user ID to payload for user-specific data access
                        user_id = None
                        if current_user.is_authenticated:
                            user_id = current_user.id
                            print(f"Using authenticated user_id: {user_id}")
                        else:
                            user_id = 0
                            print("No authenticated user, using default user_id: 0")
                        
                        payload = {
                            'text': message,
                            'source': 'user_message',  # Source type identifier for the RAG system
                            'content_id': session_id,
                            'user_id': user_id
                        }
                        
                        print(f"Sending RAG payload: {payload}")
                        
                        rag_response = requests.post(
                            direct_url,
                            json=payload,
                            headers=headers,
                            timeout=10  # Increased timeout for processing operations
                        )
                        
                        print(f"RAG direct ingest response: Status={rag_response.status_code}")
                        print(f"Response content: {rag_response.text[:500]}")
                        
                        try:
                            response_data = rag_response.json()
                            print(f"Parsed response data: {response_data}")
                        except Exception as e:
                            print(f"Failed to parse response as JSON: {e}")
                        
                        if rag_response.status_code == 200:
                            success = True
                            print("Successfully ingested user message to RAG")
                        else:
                            print(f"Failed direct RAG ingest: {rag_response.text}")
                    except Exception as e:
                        print(f"Error with RAG ingest: {e}")
                        traceback.print_exc()
                        for url in rag_urls:
                            try:
                                # Add explicit CSRF exemption header for internal requests
                                headers = {
                                    'Content-Type': 'application/json',
                                    'X-Internal-Request': 'true'  # Custom header to identify internal requests
                                }
                                
                                rag_response = requests.post(
                                    url,
                                    json={
                                        'text': message,
                                        'source': 'user_message',
                                        'content_id': session_id
                                    },
                                    headers=headers,
                                    timeout=5  # Increased timeout for more reliability
                                )
                                
                                print(f"RAG ingest response ({url}): {rag_response.status_code}")
                                
                                if rag_response.status_code == 200:
                                    success = True
                                    print(f"Successfully ingested user message to RAG via {url}")
                                    break
                                else:
                                    print(f"Failed to ingest user message. Status: {rag_response.status_code}, Response: {rag_response.text}")
                            except Exception as e:
                                print(f"Error with {url}: {e}")
                                continue
                    
                    if not success:
                        print("Warning: Failed to ingest user message to RAG")
                    
                    # Ingest AI response - simplified approach
                    success = False
                    # Ensure we have a string to send to the RAG system
                    ai_response_text = response
                    if not isinstance(response, str):
                        ai_response_text = "Response could not be converted to text"
                    
                    # Skip all direct function calls and just use simplified HTTP request
                    try:
                        # Get the server's base URL - use direct-rag-ingest only
                        base_url = request.url_root.rstrip('/')
                        direct_url = f"{base_url}/direct-rag-ingest"
                        
                        print(f"Attempting AI response RAG ingestion via direct URL: {direct_url}")
                        
                        # Add CSRF exemption headers
                        headers = {
                            'Content-Type': 'application/json',
                            'X-Internal-Request': 'true',
                            'X-CSRF-Exempt': 'true'
                        }
                        
                        # Make the request with all headers and minimal JSON
                        rag_response = requests.post(
                            direct_url,
                            json={
                                'text': ai_response_text,
                                'source': 'ai_response',
                                'content_id': session_id
                            },
                            headers=headers,
                            timeout=5
                        )
                        
                        print(f"RAG direct ingest response for AI: Status={rag_response.status_code}, Content={rag_response.text[:100]}")
                        
                        if rag_response.status_code == 200:
                            success = True
                            print("Successfully ingested AI response to RAG")
                        else:
                            print(f"Failed direct RAG ingest for AI: {rag_response.text}")
                    except Exception as e:
                        print(f"Error with AI RAG ingest: {e}")
                        traceback.print_exc()
                        for url in rag_urls:
                            try:
                                # Add explicit CSRF exemption header for internal requests
                                headers = {
                                    'Content-Type': 'application/json',
                                    'X-Internal-Request': 'true'  # Custom header to identify internal requests
                                }
                                
                                rag_response_obj = requests.post(
                                    url,
                                    json={
                                        'text': ai_response_text,
                                        'source': 'ai_response',
                                        'content_id': session_id
                                    },
                                    headers=headers,
                                    timeout=5  # Increased timeout for more reliability
                                )
                                
                                print(f"RAG ingest response for AI ({url}): {rag_response_obj.status_code}")
                                
                                if rag_response_obj.status_code == 200:
                                    success = True
                                    print(f"Successfully ingested AI response to RAG via {url}")
                                    break
                                else:
                                    print(f"Failed to ingest AI response. Status: {rag_response_obj.status_code}, Response: {rag_response_obj.text}")
                            except Exception as e:
                                print(f"Error with {url}: {e}")
                                continue
                    
                    if not success:
                        print("Warning: Failed to ingest AI response to RAG")
                except Exception as e:
                    print(f"Error ingesting chat to RAG: {e}")
                    # Don't fail the main request if RAG ingestion fails
            
        elif content_type == 'init_study_session':
            print("Processing study session initialization")
            subject = data.get("subject", message)  # Get subject from data or use message as fallback
            print(f"Initializing study session for subject: {subject}")
            response = generate_teaching_response(subject, "init_study_session")
            
            # Update context for this new study session
            context['topic'] = f"Study session: {subject}"
            context['content_type'] = 'init_study_session'
            context['subject'] = subject
            
            # Send to RAG system for ingestion
            rag_enabled = False
            try:
                if current_user.is_authenticated:
                    # First try to get it as a property
                    if hasattr(current_user, 'rag_enabled'):
                        rag_enabled = current_user.rag_enabled
                    # Then try to get it as a dictionary key
                    elif hasattr(current_user, '__getitem__') and 'rag_enabled' in current_user:
                        rag_enabled = current_user['rag_enabled']
                    # Default to True for now during development
                    else:
                        rag_enabled = True
                        print("RAG enabled by default for testing")
            except Exception as e:
                print(f"Error checking RAG status: {e}")
                rag_enabled = False
            
            if rag_enabled:
                try:
                    # Get the server's base URL - use direct-rag-ingest only
                    base_url = request.url_root.rstrip('/')
                    direct_url = f"{base_url}/direct-rag-ingest"
                    
                    print(f"Attempting study session RAG ingestion via direct URL: {direct_url}")
                    
                    # Add CSRF exemption headers
                    headers = {
                        'Content-Type': 'application/json',
                        'X-Internal-Request': 'true',
                        'X-CSRF-Exempt': 'true'
                    }
                    
                    # Get user_id for user-specific data access
                    user_id = 0
                    if current_user and current_user.is_authenticated:
                        user_id = current_user.id
                    
                    # Make the request
                    rag_response = requests.post(
                        direct_url,
                        json={
                            'text': f"Study session initiated: {subject}",
                            'source': 'study_session',
                            'content_id': session_id,
                            'user_id': user_id
                        },
                        headers=headers,
                        timeout=10
                    )
                    
                    if rag_response.status_code == 200:
                        print("Successfully ingested study session info to RAG")
                    else:
                        print(f"Failed RAG ingest for study session: {rag_response.text}")
                except Exception as e:
                    print(f"Error with study session RAG ingest: {e}")
                    # Don't fail the main request if RAG ingestion fails
            
        elif content_type == 'code':
            print("Processing code message")
            response = generate_teaching_response(message, "code")
            # Store code content for context
            context['topic'] = "Code snippet"
            context['source_content'] = message
            context['content_type'] = 'code'
            
            # Send code to RAG system
            rag_enabled = False
            try:
                if current_user.is_authenticated:
                    # First try to get it as a property
                    if hasattr(current_user, 'rag_enabled'):
                        rag_enabled = current_user.rag_enabled
                    # Then try to get it as a dictionary key
                    elif hasattr(current_user, '__getitem__') and 'rag_enabled' in current_user:
                        rag_enabled = current_user['rag_enabled']
                    # Default to True for now during development
                    else:
                        rag_enabled = True
                        print("RAG enabled by default for testing")
            except Exception as e:
                print(f"Error checking RAG status: {e}")
                rag_enabled = False
            
            if rag_enabled:
                try:
                    # Get the server's base URL
                    base_url = request.url_root.rstrip('/')
                    # Try both routes - regular and direct
                    rag_urls = [
                        f"{base_url}/rag/ingest",  # Standard route
                        f"{base_url}/direct-rag-ingest"  # Direct backup route
                    ]
                    
                    # Ingest code - simplified approach
                    success = False
                    
                    # Skip all direct function calls and just use simplified HTTP request
                    try:
                        # Get the server's base URL - use direct-rag-ingest only
                        base_url = request.url_root.rstrip('/')
                        direct_url = f"{base_url}/direct-rag-ingest"
                        
                        print(f"Attempting code RAG ingestion via direct URL: {direct_url}")
                        
                        # Add CSRF exemption headers
                        headers = {
                            'Content-Type': 'application/json',
                            'X-Internal-Request': 'true',
                            'X-CSRF-Exempt': 'true'
                        }
                        
                        # Make the request with all headers and minimal JSON
                        rag_response = requests.post(
                            direct_url,
                            json={
                                'text': message,
                                'source': 'code',
                                'content_id': session_id
                            },
                            headers=headers,
                            timeout=5
                        )
                        
                        print(f"RAG direct ingest response for code: Status={rag_response.status_code}, Content={rag_response.text[:100]}")
                        
                        if rag_response.status_code == 200:
                            success = True
                            print("Successfully ingested code to RAG")
                        else:
                            print(f"Failed direct RAG ingest for code: {rag_response.text}")
                    except Exception as e:
                        print(f"Error with code RAG ingest: {e}")
                        traceback.print_exc()
                        for url in rag_urls:
                            try:
                                # Add explicit CSRF exemption header for internal requests
                                headers = {
                                    'Content-Type': 'application/json',
                                    'X-Internal-Request': 'true'  # Custom header to identify internal requests
                                }
                                
                                rag_response = requests.post(
                                    url,
                                    json={
                                        'text': message,
                                        'source': 'code',
                                        'content_id': session_id
                                    },
                                    headers=headers,
                                    timeout=5  # Increased timeout for more reliability
                                )
                                
                                print(f"RAG ingest response for code ({url}): {rag_response.status_code}")
                                
                                if rag_response.status_code == 200:
                                    success = True
                                    print(f"Successfully ingested code to RAG via {url}")
                                    break
                                else:
                                    print(f"Failed to ingest code. Status: {rag_response.status_code}, Response: {rag_response.text}")
                            except Exception as e:
                                print(f"Error with {url}: {e}")
                                continue
                    
                    if not success:
                        print("Warning: Failed to ingest code to RAG")
                except Exception as e:
                    print(f"Error ingesting code to RAG: {e}")
                    # Don't fail the main request if RAG ingestion fails
        else:
            # Handle other message types (should be covered by the specific form handlers)
            response = generate_teaching_response(message, content_type)
        
        # Store the response in conversation context
        context['previous_responses'].append(response)
        conversation_contexts[session_id] = context
        
        # Check if response is a string before slicing
        if isinstance(response, str):
            print(f"Generated response: {response[:100]}...")
            
            # Try to parse the response as JSON if it looks like JSON
            try:
                if response.strip().startswith('{'):
                    # If it's already JSON, parse it and return as JSON object directly
                    import json
                    json_response = json.loads(response)
                    print("Parsed response as JSON object")
                    return jsonify({
                        "success": True,
                        "response": json_response,  # This already contains our structured response
                        "session_id": session_id
                    })
                else:
                    # The response might contain JSON but with extra text or formatting
                    # Try to extract JSON if it's embedded in other text
                    json_start = response.find('{')
                    json_end = response.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        try:
                            json_string = response[json_start:json_end]
                            json_response = json.loads(json_string)
                            print("Successfully extracted JSON from response")
                            return jsonify({
                                "success": True,
                                "response": json_response,
                                "session_id": session_id
                            })
                        except Exception as extract_err:
                            print(f"Failed to extract JSON: {extract_err}")
            except Exception as json_err:
                print(f"Failed to parse response as JSON: {json_err}")
                # Continue with the original response if parsing fails
        else:
            print(f"Generated response object type: {type(response)}")
        
        # Create a proper JSON response if all parsing fails
        try:
            # Create fallback JSON in our expected format
            fallback_json = {
                "response": str(response),
                "buttons": ["Ask Another Question", "Choose a Topic"]
            }
            
            return jsonify({
                "success": True, 
                "response": fallback_json,
                "session_id": session_id
            })
        except Exception as fallback_err:
            print(f"Error creating fallback JSON: {fallback_err}")
            # Last resort
            return jsonify({
                "success": True, 
                "response": {
                    "response": "I'm having trouble processing your request right now. Please try again.",
                    "buttons": ["Ask Another Question", "Choose a Topic"]
                },
                "session_id": session_id
            })
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        traceback.print_exc()
        # Return a safe error message to the client
        return jsonify({"success": False, "error": "An error occurred processing your request. Please try again."}), 500

@bot_bp.route('/process_pdf', methods=['POST'])
def process_pdf():
    """Process a PDF file and generate a teaching response"""
    # Check authentication
    if not current_user.is_authenticated:
        return jsonify({"success": False, "error": "Please log in first"}), 401
        
    try:
        session_id = request.form.get('session_id', 'default')
        
        # Check for the PDF file in different common field names
        pdf_file = None
        possible_fields = ['pdf_file', 'file', 'pdfUpload', 'pdf']
        
        for field in possible_fields:
            if field in request.files and request.files[field].filename:
                pdf_file = request.files[field]
                print(f"Found PDF file in field: {field}")
                break
        
        # If no file found in any field
        if not pdf_file:
            print("No file found in request. Fields available:", list(request.files.keys()))
            return jsonify({"error": "No PDF file found in the request"}), 400
            
        # If user does not select file, browser also submits an empty part without filename
        if pdf_file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        # Get upload folder from app config
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        # Process the PDF file
        filename = secure_filename(pdf_file.filename)
        pdf_path = os.path.join(upload_folder, filename)
        pdf_file.save(pdf_path)
        
        # Extract text from PDF with better error handling
        try:
            with open(pdf_path, 'rb') as f:
                pdf_text = extract_text_from_pdf(f)
                
                # Log the first few characters of extracted text for debugging
                if pdf_text:
                    print(f"Successfully extracted text from PDF: {pdf_text[:100]}...")
                else:
                    print("PDF text extraction returned empty result")
        except Exception as pdf_err:
            print(f"Error extracting PDF text: {pdf_err}")
            return jsonify({"error": f"Error processing PDF: {str(pdf_err)}"}), 400
        
        if not pdf_text or len(pdf_text.strip()) < 50:
            print("Insufficient text extracted from PDF")
            return jsonify({"error": "Could not extract meaningful text from the PDF"}), 400
        
        # Generate teaching response with extracted text using the session_id parameter
        response = generate_teaching_response(pdf_text, "pdf", session_id=session_id)
        
        # Create or retrieve conversation context
        if session_id not in conversation_contexts:
            conversation_contexts[session_id] = {
                'topic': f"PDF: {filename}",
                'content_type': 'pdf',
                'source_content': pdf_text,
                'previous_responses': []
            }
            context = conversation_contexts[session_id]
        else:
            context = conversation_contexts[session_id]
            context['topic'] = f"PDF: {filename}"
            context['content_type'] = 'pdf'
            context['source_content'] = pdf_text
        
        # Now context is already defined properly, just append the response
        context['previous_responses'].append(response)
        
        # Try to parse the response as JSON if it's a string
        if isinstance(response, str):
            try:
                if response.strip().startswith('{'):
                    # If it's already JSON, parse it and return as JSON object directly
                    import json
                    json_response = json.loads(response)
                    print("Parsed PDF response as JSON object")
                    return jsonify({"response": json_response, "session_id": session_id})
                else:
                    # Try to extract JSON if it's embedded in other text
                    json_start = response.find('{')
                    json_end = response.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        try:
                            json_string = response[json_start:json_end]
                            json_response = json.loads(json_string)
                            print("Successfully extracted JSON from PDF response")
                            return jsonify({"response": json_response, "session_id": session_id})
                        except Exception as extract_err:
                            print(f"Failed to extract JSON from PDF response: {extract_err}")
            except Exception as json_err:
                print(f"Failed to parse PDF response as JSON: {json_err}")
        
        # Create a proper JSON response if all parsing fails
        try:
            # Create fallback JSON in our expected format
            fallback_json = {
                "response": str(response),
                "buttons": ["Continue Learning", "I Have a Question"],
                "context": {
                    "current_section": "Document Analysis",
                    "next_section": "Key Concepts"
                }
            }
            
            return jsonify({"response": fallback_json, "session_id": session_id})
        except Exception as fallback_err:
            print(f"Error creating fallback JSON for PDF: {fallback_err}")
            # Last resort
            return jsonify({
                "response": {
                    "response": "I've analyzed your PDF but I'm having trouble formatting my response. What would you like to know about it?",
                    "buttons": ["Continue Learning", "I Have a Question"],
                    "context": {
                        "current_section": "Document Analysis",
                        "next_section": "Key Concepts"
                    }
                }, 
                "session_id": session_id
            })
            
    except Exception as e:
        import traceback
        print(f"Error in process_pdf: {str(e)}")
        traceback.print_exc()  # Print the full traceback for debugging
        return jsonify({"error": str(e)}), 500


        return jsonify({"success": False, "error": str(e)}), 500
