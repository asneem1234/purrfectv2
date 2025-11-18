"""
Eventlet patch module to fix compatibility issues with Python 3.11+ and Windows.
This addresses multiple issues:
1. "TypeError: cannot set 'is_timeout' attribute of immutable type 'TimeoutError'"
2. Windows-specific file I/O issues
3. Missing 'green' module attribute in Python 3.11+

Import this module before importing eventlet in your main application.
"""

import sys
import os
import platform
import importlib

# Import eventlet first
try:
    import eventlet
    import eventlet.timeout
except ImportError:
    print("⚠️ Eventlet not installed, skipping patches")
    eventlet = None

# Flag to check if we're on Windows
IS_WINDOWS = platform.system() == 'Windows'

print(f"Python version: {sys.version}")

# Only apply patches if we're on Python 3.11 or higher
if eventlet and sys.version_info >= (3, 11):
    import socket
    
    # Create a custom wrapper for socket.timeout
    class SocketTimeoutWrapper(socket.timeout):
        is_timeout = True
    
    # Replace the problematic patching method
    original_wrap = eventlet.timeout.wrap_is_timeout
    
    def patched_wrap_is_timeout(base):
        # Don't try to modify built-in TimeoutError
        if base is TimeoutError:
            return SocketTimeoutWrapper
        return original_wrap(base)
    
    # Apply the patch
    eventlet.timeout.wrap_is_timeout = patched_wrap_is_timeout
    
    print("✅ Applied eventlet patch for Python 3.11+ compatibility")
    
    # Fix for six module
    try:
        import inspect
        import six
        
        # Create a backup of the original function
        original_get_function_code = six.get_function_code
        
        # Define a new version that handles staticmethod correctly
        def patched_get_function_code(func):
            """Handle staticmethod objects correctly"""
            if isinstance(func, staticmethod):
                return original_get_function_code(func.__func__)
            return original_get_function_code(func)
        
        # Apply the patch
        six.get_function_code = patched_get_function_code
        print("✅ Fixed six.get_function_code for staticmethod objects")
    except Exception as e:
        print(f"⚠️ Error applying six module patch: {e}")

# Fix for eventlet.green attribute
if eventlet and not hasattr(eventlet, 'green'):
    print("Adding missing 'green' attribute to eventlet module...")
    
    # Create the module structure
    eventlet.green = importlib.import_module('eventlet.green')
    
    # Import the necessary modules
    if 'eventlet.green.thread' not in sys.modules:
        # Try to import the thread module from eventlet.green
        try:
            import eventlet.green.thread
        except ImportError:
            # Create a fallback module
            import threading
            sys.modules['eventlet.green.thread'] = threading
            eventlet.green.thread = threading
            
    # Ensure get_ident is available
    if not hasattr(eventlet.green.thread, 'get_ident'):
        eventlet.green.thread.get_ident = threading.get_ident
    
    print("✅ Fixed missing eventlet.green module")

# Windows-specific patches
if IS_WINDOWS:
    # Monkey patch GreenPipe to handle Windows limitations
    try:
        from eventlet.greenio import py3
        
        # Save the original GreenPipe function
        original_GreenPipe = py3.GreenPipe
        
        # Create a safer version that falls back to regular file I/O on errors
        def safer_GreenPipe(*args, **kwargs):
            try:
                return original_GreenPipe(*args, **kwargs)
            except (NotImplementedError, AttributeError):
                # Fall back to regular file I/O for Windows
                import io
                if isinstance(args[0], int):
                    import os
                    return io.open(os.dup(args[0]), *args[1:], **kwargs)
                return io.open(args[0], *args[1:], **kwargs)
        
        # Apply the patch
        py3.GreenPipe = safer_GreenPipe
        print("✅ Applied eventlet patch for Windows compatibility")
    except ImportError:
        print("⚠️ Could not apply Windows-specific eventlet patches")

# Fix for loading the .env file
try:
    from dotenv import load_dotenv
    print("Loading environment variables from .env file...")
    load_dotenv()
    
    # Check if GEMINI_API_KEY is available
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    if GEMINI_API_KEY:
        print(f"✅ Found GEMINI_API_KEY: {GEMINI_API_KEY[:5]}...{GEMINI_API_KEY[-5:]}")
    else:
        print("⚠️ GEMINI_API_KEY not found in environment variables")
        
        # Try to load from .env file directly
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        if os.path.exists(env_path):
            print(f"Found .env file at {env_path}")
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        try:
                            key, value = line.strip().split('=', 1)
                            if key == 'GEMINI_API_KEY':
                                os.environ['GEMINI_API_KEY'] = value
                                print(f"✅ Manually loaded GEMINI_API_KEY from .env: {value[:5]}...{value[-5:]}")
                                break
                        except ValueError:
                            # Skip lines that don't have key=value format
                            continue
except Exception as e:
    print(f"⚠️ Error checking environment variables: {e}")