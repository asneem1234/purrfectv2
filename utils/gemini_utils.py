import re
import json
from flask import current_app

# Define a global dictionary to store PDF progress
pdf_progress = {}

def get_gemini_model():
    """Get the Gemini model instance from the current app context"""
    from flask import current_app
    try:
        if hasattr(current_app, 'genai'):
            return current_app.genai.GenerativeModel('gemini-2.0-flash')
        else:
            # If not in app context or app doesn't have genai, import directly
            import google.generativeai as genai
            import os
            api_key = os.environ.get('GEMINI_API_KEY', "AIzaSyCS1Jmabh4heMRYZpKxpi3IEBnaNCorgy4")
            genai.configure(api_key=api_key)
            return genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        print(f"Error creating Gemini model: {e}")
        return None

def generate_teaching_response(content, content_type, previous_context=None, session_id=None):
    """Generate a teaching response from Gemini AI based on content type"""
    model = get_gemini_model()
    
    if model is None:
        # Provide fallback responses if model creation failed
        return f"I'm sorry, I'm having trouble accessing my knowledge base right now. Please try again in a moment."
    
    # Create appropriate prompt based on content_type
    if content_type == "chat":
        prompt = f"""
        Act as an engaging, friendly, and educational tutor called Pawfessor Meowkins. The user wants to learn about: {content}
        
        Introduce the topic briefly and explain a foundational concept. Use analogies where appropriate.
        Keep your initial explanation under 200 words.
        End by asking if the user wants to continue or has any questions about what you've covered so far.
        Remember to teach, not just summarize. Explain concepts clearly as if you're having a conversation.
        Do not switch to student mode or talk like a student.you are a teacher and you have to explain the topic in a way that is easy to understand.
        """
    
    elif content_type == "pdf":
        # Extract key topic from PDF content for better continuity
        topic_extract_prompt = f"""
        From this PDF content, extract the main topic or title in 3-5 words:
        {content[:1000]}
        """
        
        try:
            # Get the main topic to use for continuity
            topic_response = model.generate_content(topic_extract_prompt)
            topic_name = topic_response.text.strip()
            
            # Initialize PDF progress tracking with the full content
            if session_id:
                initial_chunk = manage_pdf_progress(session_id, 'init', content=content, topic=topic_name)
                # Use the initial chunk instead of arbitrary first 3000 chars
                content_chunk = initial_chunk
            else:
                content_chunk = content[:3000]
                
            prompt = f"""
            Act as an engaging, friendly, and educational tutor called Pawfessor Meowkins. The user has shared a PDF document with the following content:
            
            ---
            {content_chunk}
            ---
            
            Based on this content, introduce the main topic and explain a foundational concept from the PDF.
            Use analogies where appropriate to explain difficult concepts.
            Keep your initial explanation under 200 words.
            End by asking if the user wants to continue or has any questions about what you've covered so far.
            Remember to teach, not just summarize. Explain concepts clearly as if you're having a conversation.
            """
        except Exception:
            # If topic extraction fails, use a more generic prompt
            prompt = f"""
            Act as an engaging, friendly, and educational tutor called Pawfessor Meowkins. The user has shared a PDF document with the following content:
            
            ---
            {content[:3000]}
            ---
            
            Based on this content, introduce the main topic and explain a foundational concept from the PDF.
            Use analogies where appropriate to explain difficult concepts.
            Keep your initial explanation under 200 words.
            End by asking if the user wants to continue or has any questions about what you've covered so far.
            Remember to teach, not just summarize. Explain concepts clearly as if you're having a conversation.
            """
    
    elif content_type == "pdf_continuation":
        # Get the current progress information
        if session_id and session_id in pdf_progress:
            progress_info = pdf_progress[session_id]
            topic_name = progress_info["topic"]
            current_section = progress_info["current_section"]
            
            # Get the previous responses for context
            previous_responses = progress_info["previous_responses"]
            previous_explanations = "\n".join(previous_responses) if previous_responses else ""
            
            # Advance to the next chunk of the PDF
            next_chunk = manage_pdf_progress(session_id, 'advance')
            
            # If there's more content, create a continuation prompt
            if next_chunk:
                prompt = f"""
                Continue teaching about the PDF content. The user has indicated they want to learn more.
                
                Based on this content:
                ---
                {next_chunk}
                ---
                
                Previous explanations:
                {previous_explanations[:1000]}
                
                IMPORTANT: You must continue explaining concepts from the PDF above, not from any general knowledge.
                Do not switch topics to something unrelated to {topic_name}.
                If you've already covered the basics, move to more advanced concepts from the PDF.
                Use analogies to explain difficult concepts.
                Keep your explanation under 200 words.
                End by asking if the user wants to continue or has any questions about {topic_name}.
                """
            else:
                # We've reached the end of the PDF
                prompt = f"""
                We've now covered the main content of the PDF about {topic_name}.
                
                Based on everything we've discussed:
                
                Previous explanations:
                {previous_explanations[:1000]}
                
                Provide a concise summary of the key points covered in this PDF.
                Highlight 3-5 main takeaways that the user should remember.
                Suggest some potential applications or further areas of study related to {topic_name}.
                End by asking if the user has any questions about anything we've covered.
                """
        else:
            # Fallback if no session progress is found
            # Extract the topic if it was embedded in the content
            topic_name = "the PDF"
            topic_match = re.search(r'\[PDF_TOPIC:\s*([^\]]+)\]', content)
            if topic_match:
                topic_name = topic_match.group(1)
            
            # Get the previous explanations to track what's been covered
            previous_explanations = previous_context or ""
            
            prompt = f"""
            Continue teaching about {topic_name}. The user has indicated they want to learn more.
            
            Based on this PDF content:
            ---
            {content[:3000]}
            ---
            
            Previous explanations:
            {previous_explanations}
            
            IMPORTANT: You must continue explaining concepts from the PDF above, not from any general knowledge.
            Do not switch topics to something unrelated to {topic_name}.
            If you've already covered the basics, move to more advanced concepts from the PDF.
            Use analogies to explain difficult concepts.
            Keep your explanation under 200 words.
            End by asking if the user wants to continue or has any questions about {topic_name}.
            """
    
    elif content_type == "youtube":
        prompt = f"""
        Act as an engaging, friendly, and educational tutor called Pawfessor Meowkins. The user has shared a YouTube video with the following transcript:
        
        ---
        {content[:3000]}  # Limiting content length to avoid token issues
        ---
        
        Based on this transcript, introduce the main topic and explain a foundational concept from the video.
        Use analogies where appropriate to explain difficult concepts.
        Keep your initial explanation under 200 words.
        End by asking if the user wants to continue or has any questions about what you've covered so far.
        Remember to teach, not just summarize. Explain concepts clearly as if you're having a conversation.
        """
    
    elif content_type == "youtube_continuation":
        prompt = f"""
        Continue teaching about the video content. The user has indicated they want to learn more.
        Based on this video transcript:
        
        ---
        {content[:3000]}  # Limiting content length to avoid token issues
        ---
        
        Previous explanations:
        {previous_context}
        
        Explain the next important concept or build upon what you've already taught.
        Use analogies where appropriate to explain difficult concepts.
        Keep your explanation under 200 words.
        End by asking if the user wants to continue or has any questions.
        """
    
    elif content_type == "code":
        prompt = f"""
        Act as an engaging, friendly, and educational tutor called Pawfessor Meowkins who specializes in programming. The user has shared the following code:
        
        ```
        {content}
        ```
        
        Explain what this code does, its purpose, and a key programming concept it demonstrates.
        Use analogies where appropriate to explain difficult concepts.
        Keep your initial explanation under 200 words.
        End by asking if the user wants to continue or has any questions about what you've covered so far.
        Remember to teach, not just summarize. Explain concepts clearly as if you're having a conversation.
        """
    
    elif content_type == "continuation":
        prompt = f"""
        Continue teaching about the previous topic. The user has indicated they want to learn more.
        Explain the next important concept or build upon what you've already taught.
        Use analogies where appropriate to explain difficult concepts.
        Keep your explanation under 200 words.
        End by asking if the user wants to continue or has any questions.
        Previous context: {previous_context}
        """
    
    elif content_type == "question":
        prompt = f"""
        The user has a question about what you were teaching: {content}
        Answer their question clearly and thoroughly, using analogies if helpful.
        Keep your explanation under 200 words.
        After answering, ask if they have any further questions or if they'd like to continue with the lesson.
        Previous context: {previous_context}
        """
    else:
        # Default prompt
        prompt = f"""
        Act as an engaging, friendly, and educational tutor called Pawfessor Meowkins. The user wants to learn about: {content}
        
        Introduce the topic briefly and explain a foundational concept. Use analogies where appropriate.
        Keep your initial explanation under 200 words.
        End by asking if the user wants to continue or has any questions about what you've covered so far.
        """
    
    try:
        response = model.generate_content(prompt)
        
        # Update PDF progress with the new response if applicable
        if session_id and content_type in ["pdf", "pdf_continuation"]:
            manage_pdf_progress(session_id, 'update', response=response.text)
        
        return response.text
    except Exception as e:
        print(f"Error generating response from Gemini: {e}")
        return "I'm having trouble processing your request right now. Please try again in a moment."

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

def extract_important_topics(pdf_content, collection_name=None):
    """Extract important topics from PDF content using Gemini AI"""
    model = get_gemini_model()
    
    # Use the model to extract key topics from the PDF content
    prompt = f"""
    You are an expert academic analyzer. Read the following PDF content carefully and extract the most important topics for a student to study.
    
    For each identified topic:
    1. Assign an importance score from 1-10 (10 being most critical)
    2. Provide a brief explanation of why this topic is important
    3. Recommend study time in minutes
    4. List 2-3 key points to focus on for this topic
    
    Format your response as a JSON array with this structure:
    {{
        "topics": [
            {{
                "name": "Topic Name",
                "importance": 8,
                "explanation": "Brief explanation of the topic's importance",
                "recommended_time_minutes": 60,
                "key_points": ["Key point 1", "Key point 2", "Key point 3"]
            }},
            ...additional topics...
        ]
    }}
    
    PDF CONTENT:
    {pdf_content[:8000]}
    
    IMPORTANT: Focus only on extracting educational topics that would be useful in a study plan. Return ONLY the JSON with no additional text.
    """
    
    response = model.generate_content(prompt)
    response_text = response.text.strip()
    
    # Extract JSON from response - handle various formats the AI might return
    import json
    import re
    
    # Try direct JSON parsing first
    try:
        parsed_topics = json.loads(response_text)
        print("Successfully parsed topics as JSON")
        return parsed_topics
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        json_match = re.search(json_pattern, response_text)
        
        if json_match:
            try:
                json_str = json_match.group(1)
                parsed_topics = json.loads(json_str)
                print("Successfully extracted JSON from code block")
                return parsed_topics
            except json.JSONDecodeError:
                pass
    
    # If we reach here, try to extract from any JSON-like structure
    try:
        # Look for anything that resembles JSON object
        json_pattern = r'({[\s\S]*})'
        json_match = re.search(json_pattern, response_text)
        if json_match:
            json_str = json_match.group(1)
            # Remove any special characters that might cause parse errors
            json_str = re.sub(r'[\x00-\x1F\x7F]', '', json_str)
            parsed_topics = json.loads(json_str)
            print("Successfully extracted JSON with regex")
            return parsed_topics
    except:
        pass
        
    # If all JSON parsing fails, create structured topics from the AI response
    print("Creating structured topics from AI response")
    # Extract topic names using regex patterns
    topic_pattern = r'[\*\-•◦]?\s*([A-Z][^:]+)(?::|–|-)\s*'
    topics = re.findall(topic_pattern, response_text)
    
    # Create a structured response
    structured_topics = {
        "topics": []
    }
    
    for i, topic in enumerate(topics[:10]):  # Limit to first 10 topics
        structured_topics["topics"].append({
            "name": topic.strip(),
            "importance": 10 - (i % 3),  # Assign decreasing importance
            "explanation": f"Important topic extracted from the document",
            "recommended_time_minutes": 60 - (i * 5),  # Vary study time
            "key_points": ["Understand core concepts", "Practice with examples", "Review frequently"]
        })
    
    return structured_topics

def create_enhanced_study_schedule(form_data, topics_data):
    """Create an enhanced study schedule based on form data and topics using Gemini AI"""
    model = get_gemini_model()
    
    # Format the input data for the AI
    import json
    
    # Ensure topics_data is properly structured
    if isinstance(topics_data, list):
        if topics_data and isinstance(topics_data[0], str):
            # Convert simple topic strings to full structure
            structured_topics = []
            for i, topic in enumerate(topics_data):
                structured_topics.append({
                    "name": topic,
                    "importance": 8 - (i % 3),
                    "explanation": f"Study this topic thoroughly",
                    "recommended_time_minutes": 60,
                    "key_points": ["Understand core concepts", "Practice with examples", "Review frequently"]
                })
            topics_data = {"topics": structured_topics}
        else:
            # It's already a list of topic dictionaries
            topics_data = {"topics": topics_data}
    
    # Convert to JSON for the prompt
    try:
        form_json = json.dumps(form_data)
        topics_json = json.dumps(topics_data)
    except:
        # Handle any serialization errors
        form_json = str(form_data)
        topics_json = str(topics_data)
    
    # Create a detailed prompt for the AI
    prompt = f"""
    You are an expert study plan creator. Create a detailed daily study schedule based on these specifications:
    
    FORM DATA (including exam and preparation details):
    {form_json}
    
    TOPICS TO STUDY (with importance scores and recommended study times):
    {topics_json}
    
    Create a comprehensive study schedule following these requirements:
    1. Start on {form_data.get('startPrep')} at {form_data.get('startTime')} and end before the exam on {form_data.get('examDate')} at {form_data.get('examTime')}
    2. Include all meals: breakfast at {form_data.get('breakfastTime')}, lunch at {form_data.get('lunchTime')}, snack at {form_data.get('snackTime')}, and dinner at {form_data.get('dinnerTime')}
    3. Schedule regular breaks of {form_data.get('breakDuration')} minutes every {form_data.get('breakInterval')} hours
    4. Prioritize topics with higher importance scores
    5. Follow recommended study times for each topic
    6. Allow {form_data.get('sleepHours')} hours for sleep each night
    
    RETURN YOUR RESPONSE IN THIS EXACT JSON FORMAT:
    {{
        "plan_summary": "Brief overview of the study approach",
        "day_schedules": [
            {{
                "date": "YYYY-MM-DD",
                "formatted_date": "Month Day, Year",
                "items": [
                    {{
                        "title": "Activity name",
                        "start_time": "HH:MM",
                        "end_time": "HH:MM", 
                        "duration": minutes (as integer),
                        "type": "study|break|meal|rest",
                        "is_topic": true/false,
                        "notes": "Optional notes"
                    }}
                ]
            }}
        ]
    }}
    
    IMPORTANT: Return ONLY the JSON response with NO additional text or explanation.
    """
    
    # Call the AI to generate the schedule
    response = model.generate_content(prompt)
    response_text = response.text.strip()
    
    # Parse the JSON response
    try:
        schedule_data = json.loads(response_text)
        print("Successfully parsed schedule JSON")
        return schedule_data
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {str(e)[:100]}...")
        
        # Extract JSON from code blocks if present
        import re
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        json_match = re.search(json_pattern, response_text)
        
        if json_match:
            try:
                json_str = json_match.group(1)
                schedule_data = json.loads(json_str)
                print("Successfully extracted schedule JSON from code block")
                return schedule_data
            except json.JSONDecodeError:
                pass
        
        # Try to extract anything that looks like a JSON object
        try:
            json_pattern = r'({[\s\S]*})'
            json_match = re.search(json_pattern, response_text)
            if json_match:
                json_str = json_match.group(1)
                # Clean up the string
                json_str = json_str.replace('\\"', '"')
                json_str = re.sub(r'[\x00-\x1F\x7F]', '', json_str)
                schedule_data = json.loads(json_str)
                print("Successfully extracted schedule JSON with regex")
                return schedule_data
        except:
            pass
        
        # If all parsing attempts fail, create a minimal structure from the response
        print("Creating structured schedule from AI response")
        
        # Extract dates using regex
        date_pattern = r'(\d{4}-\d{2}-\d{2})|([A-Z][a-z]+ \d{1,2}, \d{4})'
        dates = re.findall(date_pattern, response_text)
        
        # Create basic schedule structure
        basic_schedule = {
            "plan_summary": "Study plan based on provided topics and schedule constraints",
            "day_schedules": []
        }
        
        # Try to extract plan summary
        summary_match = re.search(r'"plan_summary":\s*"([^"]+)"', response_text)
        if summary_match:
            basic_schedule["plan_summary"] = summary_match.group(1)
        
        # Create at least one day schedule if no dates were found
        if not dates:
            basic_schedule["day_schedules"].append({
                "date": form_data.get('startPrep', "2023-01-01"),
                "formatted_date": "Study Day 1",
                "items": [
                    {
                        "title": "Study Session",
                        "start_time": form_data.get('startTime', "09:00"),
                        "end_time": "10:30",
                        "duration": 90,
                        "type": "study",
                        "is_topic": True,
                        "notes": "Focus on high-priority topics"
                    }
                ]
            })
        
        return basic_schedule

def fix_broken_json(broken_json):
    """Attempt to fix broken JSON by extracting the necessary data manually"""
    try:
        import re
        
        # Create minimal structure
        result = {
            "plan_summary": "Study plan based on provided topics and schedule constraints",
            "day_schedules": []
        }
        
        # Try to extract the plan summary if it exists
        summary_match = re.search(r'"plan_summary"\s*:\s*"([^"]+)"', broken_json)
        if summary_match:
            result["plan_summary"] = summary_match.group(1)
            
        # Try to extract day schedules
        days_pattern = r'"date"\s*:\s*"([^"]+)",\s*"formatted_date"\s*:\s*"([^"]+)"'
        days_matches = re.finditer(days_pattern, broken_json)
        
        for day_match in days_matches:
            date = day_match.group(1)
            formatted_date = day_match.group(2)
            
            # Find the start and end positions for this day's items
            day_start = day_match.start()
            next_day_start = broken_json.find('"date"', day_start + 1)
            if next_day_start == -1:
                next_day_start = len(broken_json)
            
            day_content = broken_json[day_start:next_day_start]
            
            # Extract items for this day
            items = []
            items_pattern = r'"title"\s*:\s*"([^"]+)"[^}]+"start_time"\s*:\s*"([^"]+)"[^}]+"end_time"\s*:\s*"([^"]+)"[^}]+"duration"\s*:\s*(\d+)[^}]+"type"\s*:\s*"([^"]+)"[^}]+"is_topic"\s*:\s*(true|false)'
            items_matches = re.finditer(items_pattern, day_content)
            
            for item_match in items_matches:
                title = item_match.group(1)
                start_time = item_match.group(2)
                end_time = item_match.group(3)
                duration = int(item_match.group(4))
                item_type = item_match.group(5)
                is_topic = item_match.group(6) == "true"
                
                # Try to get notes if they exist
                notes_match = re.search(r'"notes"\s*:\s*"([^"]+)"', broken_json[item_match.start():item_match.start() + 500])
                notes = notes_match.group(1) if notes_match else "Study efficiently"
                
                items.append({
                    "title": title,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "type": item_type,
                    "is_topic": is_topic,
                    "notes": notes
                })
            
            # Add this day to the schedule
            if items:  # Only add days that have at least one item
                result["day_schedules"].append({
                    "date": date,
                    "formatted_date": formatted_date,
                    "items": items
                })
        
        # If we have at least one day with items, return the result
        if result["day_schedules"]:
            return result
        return None
    except Exception as e:
        print(f"Error fixing broken JSON: {e}")
        return None
