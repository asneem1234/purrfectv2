/**
 * CSRF Security Utilities for Purrfect Application
 * 
 * This file contains utilities for managing CSRF tokens in AJAX requests
 * to ensure consistent security across the application.
 */

// Get CSRF token from the page meta tag
function getCSRFToken() {
    // Look for the CSRF token in the meta tag (Flask's default location)
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        return tokenMeta.getAttribute('content');
    }
    
    // Fallback: check for hidden input field (sometimes used in forms)
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    if (tokenInput) {
        return tokenInput.value;
    }
    
    console.error('CSRF token not found in page. Security may be compromised.');
    return null;
}

/**
 * Makes an AJAX request with proper CSRF token included
 * 
 * @param {string} url - The URL to send the request to
 * @param {Object} options - Request options (method, headers, body, etc.)
 * @param {boolean} [skipCSRF=false] - Whether to skip adding CSRF token (for non-state-changing requests)
 * @returns {Promise} - Promise that resolves with the response
 */
function secureAjax(url, options = {}, skipCSRF = false) {
    // Default options
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin' // Send cookies for same-origin requests
    };
    
    // Merge with user options
    const mergedOptions = { ...defaultOptions, ...options };
    
    // Add CSRF token for state-changing requests (POST, PUT, DELETE, PATCH)
    const stateChangingMethods = ['POST', 'PUT', 'DELETE', 'PATCH'];
    if (!skipCSRF && stateChangingMethods.includes(mergedOptions.method)) {
        const token = getCSRFToken();
        if (token) {
            // Add to headers
            mergedOptions.headers = {
                ...mergedOptions.headers,
                'X-CSRFToken': token
            };
        }
    }
    
    // Return fetch promise
    return fetch(url, mergedOptions)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
            }
            return response.json();
        });
}

/**
 * Utility to initialize CSRF protection for all forms on a page
 * This helps ensure all forms have CSRF protection
 */
function initCSRFProtection() {
    // Add CSRF token to all forms that don't have it
    document.querySelectorAll('form').forEach(form => {
        // Skip if the form already has a CSRF token
        if (form.querySelector('input[name="csrf_token"]')) {
            return;
        }
        
        // Get token
        const token = getCSRFToken();
        if (token) {
            // Create hidden input
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = token;
            
            // Add to form
            form.appendChild(input);
        }
    });
    
    // Initialize listeners for dynamic form additions (optional)
    const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
            if (mutation.addedNodes && mutation.addedNodes.length > 0) {
                // Check each added node
                mutation.addedNodes.forEach(node => {
                    // If it's a form or contains forms
                    if (node.tagName === 'FORM') {
                        // Add CSRF token if needed
                        if (!node.querySelector('input[name="csrf_token"]')) {
                            const token = getCSRFToken();
                            if (token) {
                                const input = document.createElement('input');
                                input.type = 'hidden';
                                input.name = 'csrf_token';
                                input.value = token;
                                node.appendChild(input);
                            }
                        }
                    } else if (node.querySelectorAll) {
                        // Check for forms inside the node
                        node.querySelectorAll('form').forEach(form => {
                            if (!form.querySelector('input[name="csrf_token"]')) {
                                const token = getCSRFToken();
                                if (token) {
                                    const input = document.createElement('input');
                                    input.type = 'hidden';
                                    input.name = 'csrf_token';
                                    input.value = token;
                                    form.appendChild(input);
                                }
                            }
                        });
                    }
                });
            }
        });
    });
    
    // Start observing the document
    observer.observe(document.body, { childList: true, subtree: true });
    
    console.log('CSRF protection initialized for all forms');
}

// Export utilities
window.securityUtils = {
    getCSRFToken,
    secureAjax,
    initCSRFProtection
};

// Auto-initialize CSRF protection when page loads
document.addEventListener('DOMContentLoaded', function() {
    initCSRFProtection();
});