# ExamBot - AI-Powered Exam Analysis Assistant

## Overview
ExamBot (codenamed "Clawdia") is an AI-powered exam analysis assistant designed to help students understand, analyze, and improve their performance on exams. It allows users to upload exam papers in various formats (PDF, JPG, PNG), extracts the text content, and engages in an interactive conversation about the exam.

## Features
- **Exam Upload**: Supports PDF documents and images (JPG, PNG)
- **Text Extraction**: Employs multiple methods including:
  - PDF text extraction via PyMuPDF and PyPDF2
  - OCR (Optical Character Recognition) for scanned documents and images using EasyOCR
- **Interactive Chat**: Provides personalized feedback, analysis, and advice based on the exam content
- **Persistent Sessions**: Maintains conversation context throughout the chat session

## Technical Components

### Backend (exambot.py)
The backend implementation consists of a Flask Blueprint with several key routes and utilities:

#### Routes
- `/exambot` - Renders the main ExamBot interface
- `/process_exam` - Handles file uploads and initial processing
- `/exam_chat` - Manages the chat interaction with the AI

#### Text Extraction Components
1. **PDF Processing**:
   - Uses PyMuPDF (fitz) as primary extractor
   - Falls back to PyPDF2 if needed
   - For scanned PDFs, renders pages as images and applies OCR

2. **Image Processing**:
   - Uses EasyOCR for text extraction from images
   - Handles various image formats (JPG, PNG)
   - Provides feedback on extraction quality

3. **OCR Implementation**:
   - Initializes EasyOCR reader once for efficiency
   - Provides detailed feedback on OCR success and limitations
   - Handles cases where text extraction might be challenging

#### AI Response Generation
The `generate_exam_response` function:
- Integrates with Google's Generative AI (Gemini 2.0 Flash model)
- Creates context-aware prompts incorporating:
  - Exam content
  - Subject information
  - Difficulty level
  - Student's self-assessed performance
  - Conversation history
- Provides personalized, educational responses with a friendly persona
- Includes error handling for robustness

### Session Management
- Uses Flask app configuration to store and manage exam sessions
- Each upload creates a unique session with a UUID
- Stores exam content, metadata, and chat history
- Handles cases where sessions might be missing or expired

## How It Works

### Exam Upload Flow
1. User uploads an exam document via the frontend
2. System identifies the document type (PDF/image)
3. Text extraction is performed based on document type:
   - For PDFs: Direct text extraction with fallback to OCR if needed
   - For images: OCR text extraction
4. A new session is created with the extracted text and metadata
5. Initial AI greeting is generated based on content quality and type
6. Session ID is returned to the frontend for continued conversation

### Chat Flow
1. User sends a message with their session ID
2. System retrieves the associated exam session
3. The message is appended to the chat history
4. The AI generates a response using:
   - The exam content
   - Subject context
   - Previous conversation history
   - Custom prompt engineering
5. The response is stored in history and returned to frontend

## Error Handling
The system includes robust error handling for:
- Invalid file types
- OCR processing failures
- Text extraction challenges
- Session management issues
- AI response generation errors

Each error case provides appropriate fallback behavior and user feedback.

## Dependencies
- Flask and Flask-Login for web framework and authentication
- PyMuPDF (fitz) and PyPDF2 for PDF processing
- EasyOCR for image text extraction
- Google Generative AI (Gemini) for AI responses
- PIL/Pillow for image handling
- NumPy for array operations

## Persona
The ExamBot uses a friendly, supportive persona named "Clawdia" with occasional cat-themed language to create an engaging and approachable experience while delivering educational value and constructive feedback.

## Usage
The ExamBot is integrated into the main application and accessed through the `/exambot` route after user authentication. Users can upload exams, ask questions, and receive AI-powered analysis and advice.
