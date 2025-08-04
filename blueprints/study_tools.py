"""
Study Planning Tools Module

This module contains tools for creating, analyzing, and optimizing study plans.
It provides functions for:
- Estimating required study time for topics
- Checking calendar availability
- Ranking topics by importance
- Creating daily schedules
"""

from datetime import datetime, timedelta
import math

def topic_ranker_tool(topics, ranking_method='importance'):
    """
    Orders topics by importance and difficulty.
    
    Args:
        topics (list): List of topic dictionaries
        ranking_method (str, optional): Method to rank topics ('importance', 'difficulty', 'combined')
    
    Returns:
        list: Sorted topics in order of priority
    """
    if not topics:
        return []
    
    # Different ranking methods
    if ranking_method == 'importance':
        # Sort topics by importance (highest first)
        sorted_topics = sorted(topics, key=lambda x: x.get('importance', 0), reverse=True)
    elif ranking_method == 'difficulty':
        # Sort by difficulty if available, otherwise by importance
        sorted_topics = sorted(topics, key=lambda x: x.get('difficulty', x.get('importance', 0)), reverse=True)
    elif ranking_method == 'combined':
        # Combined ranking (importance * 0.7 + difficulty * 0.3)
        sorted_topics = sorted(
            topics, 
            key=lambda x: (x.get('importance', 5) * 0.7 + x.get('difficulty', 5) * 0.3), 
            reverse=True
        )
    else:
        # Default to importance
        sorted_topics = sorted(topics, key=lambda x: x.get('importance', 0), reverse=True)
    
    return sorted_topics

def topic_time_estimator(inputs):
    """
    Estimate study time required per topic based on complexity and content.
    
    Args:
        inputs (dict): A dictionary containing:
            - topics (list): List of topics with metadata
            - pdf_info (dict, optional): Information about PDF content related to topics
            - user_difficulty_ratings (dict, optional): User-provided difficulty ratings
    
    Returns:
        list: Topics with estimated time requirements in minutes
    """
    # Base study times in minutes based on importance
    base_times = {
        1: 20,   # Very low importance
        2: 25,
        3: 30,
        4: 35,
        5: 45,   # Medium importance
        6: 55,
        7: 65,
        8: 80,
        9: 95,
        10: 120  # Very high importance
    }
    
    # Default multipliers
    difficulty_multiplier = 1.0
    content_length_multiplier = 1.0
    
    estimated_topics = []
    
    for topic in inputs.get('topics', []):
        # Get topic properties with defaults
        name = topic.get('name', 'Unknown Topic')
        importance = topic.get('importance', 5)
        
        # Get base time from importance
        base_time = base_times.get(importance, 45)
        
        # Adjust for user-provided difficulty if available
        user_difficulty = inputs.get('user_difficulty_ratings', {}).get(name)
        if user_difficulty:
            difficulty_multiplier = 0.7 + (user_difficulty / 10 * 0.6)  # 0.7 to 1.3x
        
        # Adjust for PDF content length if available
        pdf_info = inputs.get('pdf_info', {})
        if name in pdf_info:
            content_pages = pdf_info[name].get('pages', 0)
            content_length_multiplier = 1.0 + min(0.5, content_pages / 20)  # Up to 1.5x for long content
        
        # Calculate recommended time in minutes
        recommended_time = int(base_time * difficulty_multiplier * content_length_multiplier)
        
        # Ensure time is reasonable (between 20 and 180 minutes)
        recommended_time = max(20, min(180, recommended_time))
        
        # Add to estimated topics
        topic_with_time = topic.copy()
        topic_with_time['recommended_time_minutes'] = recommended_time
        
        estimated_topics.append(topic_with_time)
    
    return estimated_topics

def calendar_checker(inputs):
    """
    Given start and exam dates, return total number of available days and hours per day.
    
    Args:
        inputs (dict): A dictionary containing:
            - start_date (str): Start preparation date (format: 'YYYY-MM-DD')
            - exam_date (str): Exam date (format: 'YYYY-MM-DD')
            - sleep_hours (int): Hours of sleep per day
            - meal_hours (float): Total hours spent on meals per day
            - other_commitments (list, optional): List of other commitments with dates and hours
    
    Returns:
        dict: Calendar information including:
            - total_days: Number of days between start and exam
            - available_days: Number of days available for study (excluding fully committed days)
            - hours_per_day: Average available study hours per day
            - days_needed: Estimated number of full study days needed
    """
    # Parse dates
    start_date = datetime.strptime(inputs['start_date'], '%Y-%m-%d').date()
    exam_date = datetime.strptime(inputs['exam_date'], '%Y-%m-%d').date()
    
    # Calculate total days
    total_days = (exam_date - start_date).days + 1
    
    # Calculate available hours per day
    sleep_hours = inputs.get('sleep_hours', 8)
    meal_hours = inputs.get('meal_hours', 2)
    
    # Default daily commitments (sleep + meals)
    daily_commitments = sleep_hours + meal_hours
    
    # Account for other commitments
    other_commitments = inputs.get('other_commitments', [])
    total_other_hours = 0
    fully_committed_days = 0
    
    for commitment in other_commitments:
        commitment_date = datetime.strptime(commitment['date'], '%Y-%m-%d').date()
        commitment_hours = commitment.get('hours', 0)
        
        # Check if date is within our range
        if start_date <= commitment_date <= exam_date:
            # If more than 14 hours committed on a day, consider it unavailable
            if commitment_hours + daily_commitments >= 14:
                fully_committed_days += 1
            else:
                total_other_hours += commitment_hours
    
    # Calculate available days and hours
    available_days = total_days - fully_committed_days
    
    # Calculate average available hours per day
    available_hours = 24 - daily_commitments
    avg_available_hours = available_hours - (total_other_hours / available_days if available_days > 0 else 0)
    
    # Ensure we have positive hours
    avg_available_hours = max(1, avg_available_hours)
    
    return {
        'total_days': total_days,
        'available_days': available_days,
        'hours_per_day': round(avg_available_hours, 1),
        'maximum_study_days': max(1, available_days)
    }

def calculate_total_study_hours(topics):
    """
    Calculates total hours needed to study all topics
    
    Args:
        topics (list): List of topics with recommended_time_minutes
        
    Returns:
        float: Total study hours needed
    """
    total_minutes = 0
    for topic in topics:
        # Get recommended time, default to 45 minutes if not specified
        minutes = topic.get('recommended_time_minutes', 45)
        total_minutes += minutes
    
    # Add 20% for review time
    total_minutes = total_minutes * 1.2
    total_hours = total_minutes / 60
    return total_hours

def calculate_study_days_needed(topics, available_days, hours_per_day):
    """
    Calculate how many actual study days are needed
    
    Args:
        topics (list): List of topics with recommended_time_minutes
        available_days (int): Number of days available for study
        hours_per_day (float): Average hours available per day
        
    Returns:
        int: Number of days needed for study
    """
    total_hours = calculate_total_study_hours(topics)
    
    # Determine days needed based on available study hours per day
    days_needed = total_hours / hours_per_day
    days_needed = min(available_days, round(days_needed))
    
    # Ensure at least 1 day and no more than available days
    days_needed = max(1, min(days_needed, available_days))
    return days_needed

def distribute_days_evenly(start_date, exam_date, study_days_needed):
    """
    Distribute study days evenly between start date and exam date
    
    Args:
        start_date (date): Preparation start date
        exam_date (date): Exam date
        study_days_needed (int): Number of days needed for study
        
    Returns:
        list: List of dates to study
    """
    days_available = (exam_date - start_date).days + 1
    
    # If we need all days, return all days
    if study_days_needed >= days_available:
        return [start_date + timedelta(days=i) for i in range(days_available)]
    
    # Otherwise, distribute days evenly
    if study_days_needed <= 1:
        # If only one day needed, choose the day after start (or start if that's all we have)
        if days_available > 1:
            return [start_date + timedelta(days=1)]
        return [start_date]
    
    # Calculate spacing between study days
    spacing = max(1, days_available // study_days_needed)
    study_dates = []
    
    # Generate study days with even spacing
    for i in range(study_days_needed):
        day_idx = min(i * spacing, days_available - 1)
        study_dates.append(start_date + timedelta(days=day_idx))
    
    # Always include the day before exam for review if possible
    day_before_exam = exam_date - timedelta(days=1)
    if day_before_exam >= start_date and day_before_exam not in study_dates:
        # Replace the last study day before exam day with the day before exam
        for i in range(len(study_dates) - 1, -1, -1):
            if study_dates[i] < day_before_exam:
                study_dates[i] = day_before_exam
                break
    
    return sorted(list(set(study_dates)))  # Remove duplicates and sort

def schedule_tool(inputs):
    """
    Given available hours, meals, breaks, and study blocks, output a structured timeline of a single day.
    
    Args:
        inputs (dict): A dictionary containing:
            - available_hours (int): Available hours for study in the day
            - meals (list): List of meal times and durations (e.g., [{'name': 'Breakfast', 'time': '08:00', 'duration': 30}])
            - breaks (dict): Break preferences (duration, interval)
            - study_blocks (list): List of study topics and their durations
            - wake_time (str): Time to wake up (format: 'HH:MM')
            - sleep_time (str): Time to sleep (format: 'HH:MM')
    
    Returns:
        list: Ordered list of activities for the day with start/end times
    """
    # Initialize result list
    day_activities = []
    
    # Set defaults if not provided
    wake_time = inputs.get('wake_time', '07:00')
    
    # Add wake-up
    day_activities.append({
        "title": "Wake up",
        "start_time": wake_time,
        "end_time": wake_time,
        "duration": 0,
        "type": "rest",
        "notes": "Start of day"
    })
    
    # Process meals
    for meal in inputs.get('meals', []):
        meal_time = meal.get('time')
        meal_duration = meal.get('duration', 30)
        meal_name = meal.get('name', 'Meal')
        
        meal_end_time_obj = datetime.strptime(meal_time, "%H:%M") + timedelta(minutes=meal_duration)
        meal_end_time = meal_end_time_obj.strftime("%H:%M")
        
        day_activities.append({
            "title": meal_name,
            "start_time": meal_time,
            "end_time": meal_end_time,
            "duration": meal_duration,
            "type": "meal",
            "notes": f"{meal_name} time"
        })
    
    # Current time starts after first meal (usually breakfast)
    if inputs.get('meals'):
        first_meal = inputs['meals'][0]
        current_time_obj = datetime.strptime(first_meal['time'], "%H:%M") + timedelta(minutes=first_meal.get('duration', 30) + 30)
    else:
        # Default to 9 AM if no meals defined
        current_time_obj = datetime.strptime('09:00', "%H:%M")
    
    # Process study blocks
    break_duration = inputs.get('breaks', {}).get('duration', 15)
    break_interval = inputs.get('breaks', {}).get('interval', 60)
    
    # Track study time to add breaks
    minutes_studied = 0
    
    for study_block in inputs.get('study_blocks', []):
        topic = study_block.get('topic', 'General Study')
        duration = study_block.get('duration', 45)
        importance = study_block.get('importance', 5)
        
        # Add break if needed before study session
        if minutes_studied >= break_interval:
            break_start_time = current_time_obj.strftime("%H:%M")
            break_end_time_obj = current_time_obj + timedelta(minutes=break_duration)
            break_end_time = break_end_time_obj.strftime("%H:%M")
            
            day_activities.append({
                "title": "Break",
                "start_time": break_start_time,
                "end_time": break_end_time,
                "duration": break_duration,
                "type": "break",
                "notes": "Rest and recharge"
            })
            
            current_time_obj = break_end_time_obj
            minutes_studied = 0
        
        # Add study session
        start_time = current_time_obj.strftime("%H:%M")
        end_time_obj = current_time_obj + timedelta(minutes=duration)
        end_time = end_time_obj.strftime("%H:%M")
        
        day_activities.append({
            "title": f"Study: {topic}",
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "type": "study",
            "notes": f"Focus on {topic}"
        })
        
        current_time_obj = end_time_obj
        minutes_studied += duration
    
    # Add sleep time if specified
    if 'sleep_time' in inputs:
        day_activities.append({
            "title": "Sleep Time",
            "start_time": inputs['sleep_time'],
            "end_time": wake_time,
            "duration": 480,  # Default 8 hours
            "type": "rest",
            "notes": "Sleep"
        })
    
    # Sort activities by start time
    day_activities.sort(key=lambda x: datetime.strptime(x["start_time"], "%H:%M"))
    
    return day_activities
