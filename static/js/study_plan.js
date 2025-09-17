/**
 * Study Plan JavaScript for handling data saving and manipulation
 */

// Function to save a study plan to the server
function saveStudyPlan(studyPlanData) {
    return new Promise((resolve, reject) => {
        console.log('Saving study plan data:', studyPlanData);
        
        // Make sure we have the necessary data
        if (!studyPlanData || (!studyPlanData.topics && !studyPlanData.detailed_schedule)) {
            console.error('Missing required study plan data');
            reject('Missing required study plan data');
            return;
        }
        
        // Use our secure AJAX utility to include CSRF token
        if (window.securityUtils && window.securityUtils.secureAjax) {
            // Use the secure AJAX utility
            window.securityUtils.secureAjax('/api/save_study_plan', {
                method: 'POST',
                body: JSON.stringify(studyPlanData)
            })
            .then(data => {
                console.log('Save response:', data);
                resolve(data);
            })
            .catch(error => {
                console.error('Error saving study plan:', error);
                reject(error);
            });
        } else {
            // Fallback to standard fetch with manual CSRF token
            // Get CSRF token from meta tag
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            
            // Send to the server
            fetch('/api/save_study_plan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': token || '' // Include CSRF token if available
                },
                body: JSON.stringify(studyPlanData)
            })
            .then(response => response.json())
            .then(data => {
                console.log('Save response:', data);
                resolve(data);
            })
            .catch(error => {
                console.error('Error saving study plan:', error);
                reject(error);
            });
        }
    });
}

// Helper function to extract study plan data from the page
function getStudyPlanDataFromPage() {
    // Try to find the study plan data in a data attribute or hidden field
    let studyPlanData = null;
    
    // Check for data in hidden element with ID study-plan-data
    const dataElement = document.getElementById('study-plan-data');
    if (dataElement && dataElement.getAttribute('data-plan')) {
        try {
            studyPlanData = JSON.parse(dataElement.getAttribute('data-plan'));
            return studyPlanData;
        } catch (e) {
            console.error('Error parsing study plan data from element:', e);
        }
    }
    
    // If not found, check for hidden input fields
    const topicsInput = document.querySelector('input[name="topics"]');
    const scheduleInput = document.querySelector('input[name="detailed_schedule"]');
    const examDateInput = document.querySelector('input[name="exam_date"]');
    const prepStartDateInput = document.querySelector('input[name="prep_start_date"]');
    
    if (topicsInput && scheduleInput) {
        try {
            studyPlanData = {
                topics: JSON.parse(topicsInput.value),
                detailed_schedule: JSON.parse(scheduleInput.value),
                exam_date: examDateInput ? examDateInput.value : null,
                prep_start_date: prepStartDateInput ? prepStartDateInput.value : null
            };
            return studyPlanData;
        } catch (e) {
            console.error('Error parsing study plan data from inputs:', e);
        }
    }
    
    // If all else fails, check if we have a global studyPlanData variable
    if (typeof window.studyPlanData !== 'undefined') {
        return window.studyPlanData;
    }
    
    return null;
}

// Initialize the save button functionality when the page loads
document.addEventListener('DOMContentLoaded', function() {
    const saveButton = document.getElementById('saveStudyPlanBtn');
    if (saveButton) {
        console.log('Found save button, initializing event listener');
        
        saveButton.addEventListener('click', function() {
            // Show loading state
            saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            saveButton.disabled = true;
            
            // Get study plan data
            const studyPlanData = getStudyPlanDataFromPage();
            
            if (!studyPlanData) {
                alert('Error: Could not find study plan data to save');
                saveButton.innerHTML = '<i class="fas fa-save"></i> Save Study Plan';
                saveButton.disabled = false;
                return;
            }
            
            // Save the study plan
            saveStudyPlan(studyPlanData)
                .then(data => {
                    saveButton.innerHTML = '<i class="fas fa-save"></i> Save Study Plan';
                    saveButton.disabled = false;
                    
                    if (data.success) {
                        // Show success message
                        alert('Study plan saved successfully!');
                        
                        // Redirect if needed
                        if (data.redirect) {
                            window.location.href = data.redirect;
                        }
                    } else {
                        // Show error message
                        alert('Error saving study plan: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error saving study plan:', error);
                    alert('Error saving study plan. Please try again.');
                    saveButton.innerHTML = '<i class="fas fa-save"></i> Save Study Plan';
                    saveButton.disabled = false;
                });
        });
    }
});
