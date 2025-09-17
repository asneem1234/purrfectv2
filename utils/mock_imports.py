"""
Import hooks for mock modules in deployment.
This module sets up import hooks to route imports of heavy ML libraries
to our mock implementations.
"""

import sys
import os
import importlib.util
from pathlib import Path

def setup_mock_imports():
    """
    Set up mock imports for heavy ML libraries.
    This allows the application to run without actually installing the heavy dependencies.
    """
    # Get the directory where this file is located
    current_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    
    # Dictionary mapping module names to their mock implementations
    mock_modules = {
        'sentence_transformers': current_dir / 'mock_sentence_transformers.py',
    }
    
    class MockImporter:
        def __init__(self, module_name, mock_path):
            self.module_name = module_name
            self.mock_path = mock_path
            
        def find_spec(self, fullname, path, target=None):
            # Only handle the exact module we're mocking
            if fullname != self.module_name:
                return None
                
            # Load the mock module
            spec = importlib.util.spec_from_file_location(fullname, self.mock_path)
            return spec
    
    # Register our mock importers in sys.meta_path
    for module_name, mock_path in mock_modules.items():
        sys.meta_path.insert(0, MockImporter(module_name, mock_path))
        print(f"Registered mock for {module_name} -> {mock_path}")