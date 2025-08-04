document.addEventListener('DOMContentLoaded', function() {
    console.log('Study Plan Debugging Helper loaded');
    
    // Get the study plan data from the hidden div
    const studyPlanDataElement = document.getElementById('study-plan-data');
    
    if (studyPlanDataElement) {
        try {
            const studyPlanRawData = studyPlanDataElement.getAttribute('data-plan');
            const studyPlanData = JSON.parse(studyPlanRawData);
            
            // Log to console for debugging
            console.log('Study Plan Data:', studyPlanData);
            
            // Check if schedule data exists
            if (!studyPlanData.detailed_schedule || !Array.isArray(studyPlanData.detailed_schedule) || studyPlanData.detailed_schedule.length === 0) {
                console.error('Missing or empty detailed_schedule array in study plan data');
                displayAlert('No schedule data found. Please generate a new study plan.');
            } else {
                console.log('Schedule days:', studyPlanData.detailed_schedule.length);
                
                // Check and fix activities for each day in the schedule
                let activitiesAdded = false;
                studyPlanData.detailed_schedule.forEach((day, dayIndex) => {
                    if (!day.activities || !Array.isArray(day.activities) || day.activities.length === 0) {
                        console.warn(`Day ${dayIndex + 1} (${day.formatted_date}) has no activities - generating from topics`);
                        
                        // Generate activities from topics
                        if (studyPlanData.topics && studyPlanData.topics.length > 0) {
                            console.log(`Generating activities from ${studyPlanData.topics.length} available topics`);
                            day.activities = generateActivitiesFromTopics(studyPlanData.topics, day, dayIndex);
                            activitiesAdded = true;
                        } else {
                            console.log('No topics available, creating default activities');
                            day.activities = generateDefaultActivities(day);
                            activitiesAdded = true;
                        }
                    } else {
                        console.log(`Day ${dayIndex + 1} (${day.formatted_date}) already has ${day.activities.length} activities`);
                    }
                });
                
                if (activitiesAdded) {
                    console.log('Activities were added to the schedule - updating global data');
                    // Update the global scheduleData variable used by the UI
                    window.scheduleData = studyPlanData.detailed_schedule;
                }
                
                // Force render the checklist after ensuring data is available
                if (typeof renderChecklist === 'function') {
                    console.log('Forcing checklist rendering');
                    renderChecklist(0);
                    
                    // Update the progress display after rendering
                    if (typeof updateChecklistProgress === 'function') {
                        setTimeout(updateChecklistProgress, 100);
                    }
                }
            }
        } catch (error) {
            console.error('Error parsing study plan data:', error);
            displayAlert('There was an error loading your study plan. Please try refreshing the page.');
        }
    } else {
        console.error('Study plan data element not found');
    }
    
    // Function to generate activities from topics
    function generateActivitiesFromTopics(topics, day, dayIndex) {
        const activities = [];
        const startHour = 9; // Start at 9 AM
        let currentHour = startHour;
        
        // Determine how many topics to include per day
        const daysCount = window.scheduleData ? window.scheduleData.length : 3;
        const topicsPerDay = Math.ceil(topics.length / daysCount); 
        const startIndex = dayIndex * topicsPerDay;
        const endIndex = Math.min(startIndex + topicsPerDay, topics.length);
        const dayTopics = topics.slice(startIndex, endIndex);
        
        console.log(`Creating activities for ${dayTopics.length} topics (${startIndex}-${endIndex-1} of ${topics.length})`);
        
        // Create an activity for each topic
        dayTopics.forEach((topic, index) => {
            // Calculate time slots
            const duration = Math.max(30, Math.min(120, topic.recommended_time_minutes || 60)); // Min 30, max 120 minutes
            const startTime = formatTime(currentHour, 0);
            
            const hours = Math.floor(duration / 60);
            const minutes = duration % 60;
            
            let endHour = currentHour + hours;
            const endMinutes = minutes;
            
            const endTime = formatTime(endHour, endMinutes);
            
            // Move to next time slot (add 15 minute break)
            currentHour = endHour;
            if (endMinutes > 0) {
                currentHour += 1;
            }
            
            // Create the activity
            activities.push({
                title: `Study ${topic.name}`,
                type: 'study',
                start_time: startTime,
                end_time: endTime,
                duration: duration,
                notes: topic.key_points && topic.key_points.length > 0 ? 
                    `Focus on: ${topic.key_points.slice(0, 2).join(', ')}` : 
                    `Importance: ${topic.importance}/10`
            });
            
            // Add a short break after each topic (except the last one)
            if (index < dayTopics.length - 1) {
                const breakStartTime = formatTime(currentHour, 0);
                const breakEndTime = formatTime(currentHour + 0.5, 0); // 30 min break
                
                activities.push({
                    title: 'Quick Break',
                    type: 'break',
                    start_time: breakStartTime,
                    end_time: breakEndTime,
                    duration: 30,
                    notes: 'Take a short break to refresh your mind'
                });
                
                currentHour += 0.5; // Advance 30 minutes
            }
        });
        
        // If we have room, add a final review session
        if (dayTopics.length > 0) {
            const reviewStartTime = formatTime(currentHour, 0);
            const reviewEndTime = formatTime(currentHour + 1, 0);
            
            activities.push({
                title: 'Review Session',
                type: 'review',
                start_time: reviewStartTime,
                end_time: reviewEndTime,
                duration: 60,
                notes: 'Review what you learned today and reinforce key concepts'
            });
        }
        
        return activities;
    }
    
    // Function to generate default activities if no topics
    function generateDefaultActivities(day) {
        return [
            {
                title: 'Study Session',
                type: 'study',
                start_time: '09:00',
                end_time: '10:30',
                duration: 90,
                notes: 'Focus on course materials and take notes'
            },
            {
                title: 'Short Break',
                type: 'break',
                start_time: '10:30',
                end_time: '11:00',
                duration: 30,
                notes: 'Take a refreshing break'
            },
            {
                title: 'Practice Problems',
                type: 'practice',
                start_time: '11:00',
                end_time: '12:30',
                duration: 90,
                notes: 'Work through practice questions and exercises'
            },
            {
                title: 'Lunch Break',
                type: 'break',
                start_time: '12:30',
                end_time: '13:30',
                duration: 60,
                notes: 'Take a proper lunch break'
            },
            {
                title: 'Review Session',
                type: 'review',
                start_time: '13:30',
                end_time: '15:00',
                duration: 90,
                notes: 'Consolidate your learning and identify any gaps'
            }
        ];
    }
    
    // Helper function to format time (handles hours with decimal points for 30min increments)
    function formatTime(hours, minutes) {
        // Handle decimal hours (like 9.5 = 9:30)
        if (hours % 1 !== 0) {
            minutes = 30;
            hours = Math.floor(hours);
        }
        
        const paddedHours = Math.floor(hours).toString().padStart(2, '0');
        const paddedMinutes = minutes.toString().padStart(2, '0');
        return `${paddedHours}:${paddedMinutes}`;
    }
    
    function displayAlert(message) {
        // Create a user-friendly alert at the top of the page
        const alertElement = document.createElement('div');
        alertElement.className = 'study-plan-alert';
        alertElement.style.cssText = `
            background-color: #fff3cd;
            color: #856404;
            padding: 15px;
            margin: 15px auto;
            border-radius: 10px;
            border-left: 5px solid #ffc107;
            max-width: 800px;
            text-align: center;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        `;
        alertElement.innerHTML = `
            <strong>⚠️ Attention:</strong> ${message}
            <div style="margin-top: 10px;">
                <a href="/forms" style="
                    background-color: #ff85b4;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 20px;
                    text-decoration: none;
                    font-size: 14px;
                ">Create New Study Plan</a>
            </div>
        `;
        
        // Insert at the top of the container
        const container = document.querySelector('.container');
        if (container) {
            container.insertBefore(alertElement, container.firstChild);
        } else {
            document.body.insertBefore(alertElement, document.body.firstChild);
        }
    }
    
    // Add additional function to manually fix the schedule if the automatic approach doesn't work
    window.fixStudySchedule = function() {
        console.log("Manually fixing study schedule...");
        
        const studyPlanElement = document.getElementById('study-plan-data');
        if (!studyPlanElement) {
            console.error("Could not find study plan data element");
            return;
        }
        
        try {
            const data = JSON.parse(studyPlanElement.getAttribute('data-plan'));
            if (!data.topics || data.topics.length === 0) {
                console.error("No topics found in study plan data");
                return;
            }
            
            // Create activities from topics for each day
            if (data.detailed_schedule) {
                data.detailed_schedule.forEach((day, index) => {
                    day.activities = generateActivitiesFromTopics(data.topics, day, index);
                });
                
                // Update global variable
                window.scheduleData = data.detailed_schedule;
                
                // Re-render the first day
                if (typeof renderChecklist === 'function') {
                    renderChecklist(0);
                }
                
                console.log("Schedule fixed! Activities generated from topics.");
            }
        } catch (error) {
            console.error("Error fixing schedule:", error);
        }
    };
    
    // Run the manual fix after a short delay if no activities are found
    setTimeout(() => {
        const container = document.getElementById('schedule-container');
        if (container && container.textContent.includes('No activities scheduled for this day')) {
            console.log("No activities found after initial load, running manual fix...");
            window.fixStudySchedule();
        }
    }, 1000);
});
