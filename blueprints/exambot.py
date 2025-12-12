from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, session, flash
from flask_login import login_required, current_user
import os
import json
from werkzeug.utils import secure_filename
import datetime
import tempfile
import google.generativeai as genai
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
import io
import uuid
import traceback
import PyPDF2  # Add PyPDF2 for PDF processing
import time

# Lazy loading for heavy libraries (EasyOCR requires torch which is huge)
_easyocr = None

def _get_easyocr():
    """Lazy load easyocr module only when needed"""
    global _easyocr
    if _easyocr is None:
        try:
            import easyocr
            _easyocr = easyocr
            print("EasyOCR module loaded successfully")
        except ImportError as e:
            print(f"Warning: EasyOCR not available - OCR features disabled: {e}")
            _easyocr = False
    return _easyocr if _easyocr else None

# Create exam bot blueprint
exambot_bp = Blueprint('exambot_bp', __name__)

# Store session data for exam analysis - using Flask app config to ensure persistence
def get_exam_sessions():
    """Get exam sessions from Flask app config or initialize if needed"""
    if not hasattr(current_app, 'exam_sessions'):
        current_app.exam_sessions = {}
    return current_app.exam_sessions

# EasyOCR reader - initialize once and reuse (lazy loaded)
_ocr_reader = None

def get_ocr_reader():
    """Get or initialize the EasyOCR reader (lazy loaded)"""
    global _ocr_reader
    if _ocr_reader is None:
        easyocr = _get_easyocr()
        if easyocr is None:
            print("EasyOCR not available - cannot initialize OCR reader")
            return None
        print("Initializing EasyOCR reader...")
        # Initialize for English only
        _ocr_reader = easyocr.Reader(['en'], gpu=False)
    return _ocr_reader

def extract_text_from_image(image_path):
    """Extract text from image files using EasyOCR (lazy loaded)"""
    try:
        # Check if EasyOCR is available
        reader = get_ocr_reader()
        if reader is None:
            return "[OCR feature not available. EasyOCR library is not installed. Please describe the image content manually.]"
        
        print(f"Processing image file with EasyOCR: {image_path}")
        start_time = time.time()
        
        # Load image with PIL
        img = Image.open(image_path)
        
        # Convert to RGB if needed (EasyOCR requires RGB)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Get OCR reader
        reader = get_ocr_reader()
        
        # Perform OCR
        results = reader.readtext(np.array(img))
        
        # Extract text from results
        if not results:
            print("No text detected in image")
            return f"[Image processed but no text could be detected. The image may not contain readable text or the quality might be too low.]"
        
        # Compile all detected text
        extracted_text = ""
        for detection in results:
            # Each detection is a tuple: (bounding_box, text, confidence)
            text = detection[1]
            confidence = detection[2]
            
            # Add to extracted text if confidence is reasonable
            if confidence > 0.3:  # Adjust this threshold as needed
                extracted_text += text + " "
        
        # Clean up text
        extracted_text = extracted_text.strip()
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"OCR completed in {processing_time:.2f} seconds. Extracted {len(extracted_text)} characters.")
        
        if not extracted_text:
            return f"[Image processed but no clear text could be detected. Please describe what's in the image or ask specific questions about it.]"
            
        return extracted_text
    except Exception as e:
        print(f"Error processing image with OCR: {str(e)}")
        traceback.print_exc()
        return f"[Error processing image: {str(e)}. The image was received but couldn't be processed with OCR.]"

@exambot_bp.route('/exambot')
@login_required
def exambot():
    """Render the exam bot page"""
    return render_template('exambot.html', user=current_user)

@exambot_bp.route('/process_exam', methods=['POST'])
@login_required
def process_exam():
    """Process an uploaded exam paper"""
    try:
        print("Received process_exam request")
        print("Current user:", current_user.username if current_user and current_user.is_authenticated else "Not authenticated")
        # Print all form fields for debugging
        print("Form fields:", list(request.form.keys()))
        print("Files:", list(request.files.keys()))
        
        if 'exam_file' not in request.files:
            print("ERROR: No file in request")
            return jsonify({"success": False, "error": "No file part in the request. Please select a file to upload."}), 400
        
        file = request.files['exam_file']
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({"success": False, "error": "No file selected. Please choose a file to upload."}), 400
        
        # Get exam details from form
        exam_info = {}
        if 'exam_info' in request.form:
            try:
                exam_info = json.loads(request.form.get('exam_info'))
            except Exception as e:
                print(f"Error parsing exam_info: {e}")
                
        subject = exam_info.get('subject', 'Unknown Subject')
        duration = exam_info.get('duration', '0')
        difficulty = exam_info.get('difficulty', 'medium')
        performance = exam_info.get('performance', 'average')
        
        print(f"Processing exam for subject: {subject}, difficulty: {difficulty}")
        
        # Save file to temporary location
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(file_path)
        print(f"File saved to temporary location: {file_path}")
        
        # Determine file type
        file_type = file.filename.split('.')[-1].lower()
        print(f"File type detected from extension: {file_type}")
        
        # Initialize exam_text
        exam_text = ""
        
        # Process based on file type
        if file_type in ['pdf']:
            try:
                print(f"PROCESSING PDF: Extracting text from PDF using PyMuPDF and/or PyPDF2")
                
                # Try PyMuPDF first (usually better quality extraction)
                try:
                    pdf_document = fitz.open(file_path)
                    for page_num in range(len(pdf_document)):
                        page = pdf_document[page_num]
                        page_text = page.get_text()
                        exam_text += page_text + "\n\n"
                    pdf_document.close()
                except Exception as e:
                    print(f"PyMuPDF extraction failed, trying PyPDF2: {e}")
                    
                    # Fallback to PyPDF2 if PyMuPDF fails
                    with open(file_path, 'rb') as pdf_file:
                        reader = PyPDF2.PdfReader(pdf_file)
                        for page_num in range(len(reader.pages)):
                            page_text = reader.pages[page_num].extract_text()
                            if page_text:  # Check if page text is not empty
                                exam_text += page_text + "\n\n"
                
                # Check if we got meaningful text - if not, the PDF may be scanned
                if not exam_text or len(exam_text.strip()) < 100:
                    print("Minimal text extracted. PDF may be scanned. Trying OCR on PDF images...")
                    
                    # Extract images from PDF and perform OCR
                    ocr_text = ""
                    pdf_document = fitz.open(file_path)
                    
                    for page_num in range(len(pdf_document)):
                        page = pdf_document[page_num]
                        # Get images from page
                        image_list = page.get_images(full=True)
                        
                        if not image_list:
                            # If no images found, try rendering page as image
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
                            img_path = os.path.join(temp_dir, f"page_{page_num}.png")
                            pix.save(img_path)
                            
                            # OCR the rendered page
                            page_text = extract_text_from_image(img_path)
                            ocr_text += page_text + "\n\n"
                            
                            # Clean up
                            os.remove(img_path)
                        else:
                            # Process each image found in the page
                            for img_index, img in enumerate(image_list):
                                xref = img[0]
                                base_image = pdf_document.extract_image(xref)
                                image_bytes = base_image["image"]
                                
                                # Save image temporarily
                                img_path = os.path.join(temp_dir, f"image_{page_num}_{img_index}.png")
                                with open(img_path, "wb") as img_file:
                                    img_file.write(image_bytes)
                                
                                # OCR the image
                                image_text = extract_text_from_image(img_path)
                                if image_text and not image_text.startswith("["):  # Check if valid text was extracted
                                    ocr_text += image_text + "\n\n"
                                
                                # Clean up
                                os.remove(img_path)
                    
                    pdf_document.close()
                    
                    if ocr_text.strip():
                        print(f"OCR extracted {len(ocr_text)} characters from PDF images")
                        exam_text = ocr_text
                
                # Validate extracted text
                print(f"EXTRACTION COMPLETE: Total {len(exam_text)} characters extracted from PDF")
                if not exam_text or len(exam_text.strip()) < 50:
                    print("WARNING: Minimal text extracted from PDF")
                    return jsonify({
                        "success": False, 
                        "error": "Could not extract sufficient text from PDF file. The file may be scanned, corrupted, or contain no text content."
                    }), 400
                
            except Exception as e:
                print(f"ERROR extracting PDF text: {str(e)}")
                traceback.print_exc()
                return jsonify({"success": False, "error": f"Could not process PDF file: {str(e)}"}), 400
                
        elif file_type in ['jpg', 'jpeg', 'png']:
            try:
                print(f"PROCESSING IMAGE: Using EasyOCR for text extraction")
                
                # Extract text using EasyOCR
                exam_text = extract_text_from_image(file_path)
                
                # Create a session ID
                session_id = f"exam_{uuid.uuid4().hex}"
                exam_sessions = get_exam_sessions()
                
                # Get word count for extracted text
                word_count = len(exam_text.split()) if exam_text else 0
                print(f"OCR extracted {word_count} words from the image")
                
                # Store exam details with extracted text
                exam_sessions[session_id] = {
                    'subject': subject,
                    'duration': duration,
                    'difficulty': difficulty,
                    'performance': performance,
                    'exam_text': exam_text,
                    'file_type': file_type,
                    'word_count': word_count,
                    'chat_history': [],
                    'created_at': datetime.datetime.utcnow()
                }
                
                # Determine initial response based on OCR success
                if word_count > 20:  # If we got a reasonable amount of text
                    initial_response = (
                        f"I've analyzed your {subject} exam image and extracted the text content. "
                        f"What specific aspects of this exam would you like me to help with?"
                    )
                else:  # If OCR didn't find much text
                    initial_response = (
                        f"I've received your {subject} exam image, but I could only extract limited text. "
                        f"Please describe what's shown in the image or ask specific questions about the content."
                    )
                
                exam_sessions[session_id]['chat_history'].append({"role": "assistant", "content": initial_response})
                
                return jsonify({
                    "success": True,
                    "response": initial_response,
                    "session_id": session_id,
                    "content_type": file_type,
                    "ocr_word_count": word_count,
                    "extractedText": exam_text
                })
                
            except Exception as e:
                # Catch-all exception handler
                print(f"ERROR processing image with OCR: {str(e)}")
                traceback.print_exc()
                
                # Still create a session - don't let failure stop the conversation
                session_id = f"exam_{uuid.uuid4().hex}"
                exam_sessions = get_exam_sessions()
                
                # Use a placeholder for the exam text
                exam_text = f"[Image file uploaded: {file.filename}. OCR processing error: {str(e)}]"
                
                exam_sessions[session_id] = {
                    'subject': subject,
                    'duration': duration,
                    'difficulty': difficulty,
                    'performance': performance,
                    'exam_text': exam_text,
                    'file_type': file_type,
                    'chat_history': [],
                    'created_at': datetime.datetime.utcnow()
                }
                
                initial_response = (
                    f"I've received your {subject} exam image but encountered an error with the OCR processing. "
                    f"I'll still try to help - please describe what's in the image or ask specific questions about your exam."
                )
                
                exam_sessions[session_id]['chat_history'].append({"role": "assistant", "content": initial_response})
                
                return jsonify({
                    "success": True,
                    "warning": f"OCR processing error: {str(e)}",
                    "response": initial_response,
                    "session_id": session_id
                })
        else:
            return jsonify({
                "success": False, 
                "error": f"Unsupported file type: {file_type}. Please upload a PDF, JPG, or PNG file."
            }), 400
        
        # Create a unique session ID for this exam chat
        session_id = f"exam_{uuid.uuid4().hex}"
        
        # Store exam details in our session dictionary
        exam_sessions = get_exam_sessions()
        
        # Debug - text statistics for prompt engineering
        word_count = len(exam_text.split())
        line_count = len(exam_text.splitlines())
        print(f"Text stats: {word_count} words, {line_count} lines")
        
        # Check if OCR was used
        ocr_used = file_type in ['jpg', 'jpeg', 'png'] or (file_type == 'pdf' and len(exam_text.strip()) >= 100)
        
        # Save extracted text and metadata
        exam_sessions[session_id] = {
            'subject': subject,
            'duration': duration,
            'difficulty': difficulty,
            'performance': performance,
            'exam_text': exam_text,
            'file_type': file_type,
            'word_count': word_count,
            'ocr_used': ocr_used,
            'chat_history': [],
            'created_at': datetime.datetime.utcnow()
        }
        
        print(f"Exam session created with ID: {session_id}")
        print(f"Active sessions after upload: {list(exam_sessions.keys())}")
        
        # Determine appropriate initial response based on content
        if file_type in ['jpg', 'jpeg', 'png']:
            initial_response = f"I've received your {subject} exam image. What specific aspects would you like to discuss? You can ask about particular questions visible in the image or general strategies for this subject."
        else:
            initial_response = f"I've analyzed your {subject} exam document. What specific aspects would you like to discuss? For example, you can ask about particular questions, overall performance, or improvement strategies."
        
        # Add initial greeting to chat history
        exam_sessions[session_id]['chat_history'].append({"role": "assistant", "content": initial_response})
        
        return jsonify({
            "success": True,
            "response": initial_response,
            "session_id": session_id,
            "content_type": file_type,
            "extractedText": exam_text
        })
        
    except Exception as e:
        print(f"CRITICAL ERROR processing exam paper: {str(e)}")
        traceback.print_exc()  # Print full stack trace for debugging
        return jsonify({"success": False, "error": str(e)}), 500

@exambot_bp.route('/exam_chat', methods=['POST'])
@login_required
def exam_chat():
    """Handle exam bot chat messages"""
    try:
        print("Received exam_chat request")
        data = request.get_json()
        print("Request data:", data)
        
        if not data or 'message' not in data:
            print("Invalid request data:", data)
            return jsonify({"success": False, "error": "Invalid request data"}), 400
        
        message = data['message']
        
        # Get questions and answers if provided
        questions = data.get('questions', [])
        answers = data.get('answers', {})
        
        # Get session_id from request
        session_id = data.get('session_id')
        
        # Get our session store
        exam_sessions = get_exam_sessions()
        print(f"Current active sessions: {list(exam_sessions.keys())}")
        
        # Debug: print all active sessions
        if not exam_sessions:
            print("No active exam sessions found")
            # Create a new default session if none exists
            session_id = f"exam_{uuid.uuid4().hex}"
            exam_sessions[session_id] = {
                'subject': 'General',
                'duration': '60',
                'difficulty': 'medium',
                'performance': 'average',
                'exam_text': 'No exam data provided. Starting a general discussion.',
                'chat_history': [],
                'created_at': datetime.datetime.utcnow()
            }
            print(f"Created new default session: {session_id}")
            
            # Add initial greeting
            initial_response = "Hello! It seems you haven't uploaded an exam yet. I'd be happy to discuss general exam strategies or you can upload an exam for specific feedback."
            exam_sessions[session_id]['chat_history'].append({"role": "assistant", "content": initial_response})
            
            # Add the user's first message
            exam_sessions[session_id]['chat_history'].append({"role": "user", "content": message})
            
            # Generate a helpful response
            response = "I notice you haven't uploaded an exam document yet. If you'd like specific feedback, please upload your exam using the panel on the left. In the meantime, I can offer general advice about exam preparation and performance improvement. What specific concerns do you have about your exam experience?"
            
            # Add response to chat history
            exam_sessions[session_id]['chat_history'].append({"role": "assistant", "content": response})
            
            return jsonify({
                "success": True,
                "response": response,
                "session_id": session_id,
                "note": "Created new session as no exam was uploaded"
            })
        
        # If no session_id is provided, use the most recent session
        if not session_id:
            print("No session_id provided, trying to use most recent session")
            try:
                # Sort sessions by creation time and get the most recent
                if exam_sessions:
                    latest_session_id = sorted(
                        exam_sessions.keys(),
                        key=lambda sid: exam_sessions[sid].get('created_at', datetime.datetime.min),
                        reverse=True
                    )[0]
                    session_id = latest_session_id
                    print(f"Using most recent session: {session_id}")
                else:
                    return jsonify({"success": False, "error": "No active exam sessions. Please upload an exam first."}), 400
            except Exception as e:
                print(f"Error finding most recent session: {e}")
                return jsonify({"success": False, "error": "Session error. Please upload an exam first."}), 400
        
        # Check if the session exists
        if session_id not in exam_sessions:
            print(f"Session ID {session_id} not found in exam_sessions")
            return jsonify({
                "success": False, 
                "error": "Invalid session ID. Please refresh and try again.",
                "available_sessions": list(exam_sessions.keys())
            }), 400
        
        exam_session = exam_sessions[session_id]
        print(f"Found exam session data: subject={exam_session['subject']}")
        
        # Store questions and answers if provided
        if questions and len(questions) > 0:
            exam_session['questions'] = questions
            print(f"Stored {len(questions)} questions in session")
        
        if answers and len(answers) > 0:
            exam_session['answers'] = answers
            print(f"Stored answers for {len(answers)} questions in session")
            
        # Add user message to chat history
        exam_session['chat_history'].append({"role": "user", "content": message})
        
        # Generate response using Gemini with improved question handling
        print("Generating response with Gemini...")
        response = generate_exam_response(exam_session, message)
        print(f"Got response: {response[:50]}...")
        
        # Add bot response to chat history
        exam_session['chat_history'].append({"role": "assistant", "content": response})
        
        # Update session with new chat history
        exam_sessions[session_id] = exam_session

        return jsonify({
            "success": True,
            "response": response,
            "session_id": session_id  # Return session_id so client can use it in future requests
        })
        
    except Exception as e:
        print(f"Error in exam chat: {str(e)}")
        traceback.print_exc()  # Print full stack trace for debugging
        return jsonify({"success": False, "error": str(e)}), 500

def generate_exam_response(exam_session, user_message):
    """Generate a response to the user's message about their exam"""
    try:
        subject = exam_session['subject']
        duration = exam_session['duration']
        difficulty = exam_session['difficulty']
        performance = exam_session['performance']
        exam_text = exam_session['exam_text']
        chat_history = exam_session['chat_history']
        
        # Get extracted questions and user answers if available
        questions = exam_session.get('questions', [])
        answers = exam_session.get('answers', {})
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        # More flexible approach to question identification
        # Instead of strict pattern matching, we'll use a more general prompt
        # that helps the model interpret the user's question in context
        
        # Extract potential topics or question numbers without strict formatting
        general_instruction = """
        The student may be asking about specific exam questions, topics, or seeking general advice.
        
        If they mention specific question numbers, parts, or sections of the exam:
        1. Try to locate that content in the exam text
        2. Focus your response on that specific question or section
        3. Provide detailed feedback about what a good answer would include
        
        If they're asking for general feedback or advice:
        1. Give supportive and constructive guidance based on the exam content
        2. Suggest specific study strategies relevant to the subject
        
        If they express concerns about their performance:
        1. Be encouraging and empathetic
        2. Offer practical improvement suggestions
        
        Remember that students may phrase their questions in many different ways - be flexible in your interpretation.
        """
        
        # Build the context from exam details and chat history
        conversation_history = ""
        for message in chat_history[:-1]:  # Exclude the latest message which we're processing
            role_prefix = "Student" if message["role"] == "user" else "Exam Bot"
            conversation_history += f"{role_prefix}: {message['content']}\n\n"
        
        # Build information about questions and answers
        questions_and_answers = ""
        if questions and len(questions) > 0:
            questions_and_answers += "\nEXTRACTED QUESTIONS:\n"
            for i, q in enumerate(questions):
                questions_and_answers += f"Question {i+1}: {q}\n"
                
                # Add user's answer if available
                if answers and str(i+1) in answers:
                    questions_and_answers += f"Student's Answer: {answers[str(i+1)]}\n\n"
                else:
                    questions_and_answers += "Student's Answer: Not provided\n\n"
        
        # Build the prompt
        prompt = f"""
        You are Clawdia, a helpful and supportive AI exam analysis assistant. You have a friendly, slightly quirky personality with occasional cat-themed language.
        
        EXAM DETAILS:
        Subject: {subject}
        Duration: {duration} minutes
        Difficulty: {difficulty}
        Student's self-assessed performance: {performance}
        
        EXAM CONTENT:
        {exam_text[:5000]}  # Limited to first 5000 chars for token reasons
        
        {questions_and_answers}
        
        PREVIOUS CONVERSATION:
        {conversation_history}
        
        STUDENT'S LATEST QUESTION:
        {user_message}
        
        {general_instruction}
        
        Provide a helpful, educational response that:
        1. Addresses the student's specific question about their exam
        2. Gives constructive feedback and specific suggestions
        3. If they ask about a specific exam question, provide what a good answer should include with detailed content
        4. If they express frustration or disappointment, be empathetic and offer improvement strategies
        5. If they're satisfied with their performance, acknowledge their success and suggest how to build on it
        
        Your response should be supportive, specific to their exam, and focus on improvement. Use a few cat-themed phrases occasionally (like "purr-fect understanding" or "that's the right meow-ndset") to maintain your unique personality.
        
        Keep your response under 300 words unless more detail is necessary.
        """
        
        # Generate response
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error generating exam response: {e}")
        return "I'm sorry, I'm having trouble analyzing your exam right now. Please try asking another question or try again later."