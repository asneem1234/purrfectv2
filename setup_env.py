#!/usr/bin/env python
"""
Environment Setup Script for Purrfect Platform
----------------------------------------------
This script generates secure API keys and sets up environment variables
for development and production environments.
"""

import os
import secrets
import argparse
import platform

def generate_secure_key(length=32):
    """Generate a cryptographically secure random key"""
    return secrets.token_urlsafe(length)

def create_env_file(env_vars, filename='.env'):
    """Create or update .env file with environment variables"""
    # Read existing env file if it exists
    existing_vars = {}
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    existing_vars[key] = value

    # Update with new variables, preserving existing ones
    existing_vars.update(env_vars)
    
    # Write back to file
    with open(filename, 'w') as f:
        for key, value in existing_vars.items():
            f.write(f"{key}={value}\n")
    
    print(f"Environment variables written to {filename}")

def setup_dev_environment():
    """Set up development environment variables"""
    env_vars = {
        'FLASK_ENV': 'development',
        'FLASK_DEBUG': '1',
        'SECRET_KEY': generate_secure_key(),
        'SERVER_API_KEY': generate_secure_key(),
        # Add more variables as needed
    }
    
    # Check if GEMINI_API_KEY already exists and prompt if not
    if 'GEMINI_API_KEY' not in os.environ:
        print("\nNOTE: GEMINI_API_KEY is not set in your environment.")
        choice = input("Would you like to add a GEMINI_API_KEY to the .env file? (y/n): ")
        if choice.lower() == 'y':
            key = input("Enter your Gemini API key: ")
            if key:
                env_vars['GEMINI_API_KEY'] = key

    create_env_file(env_vars)
    
    # Print commands to set environment variables for current session
    print("\nTo set environment variables for your current terminal session:")
    if platform.system() == 'Windows':
        print("\nFor Windows CMD:")
        for key, value in env_vars.items():
            print(f"set {key}={value}")
        
        print("\nFor Windows PowerShell:")
        for key, value in env_vars.items():
            print(f"$env:{key} = \"{value}\"")
    else:
        print("\nFor Linux/macOS:")
        for key, value in env_vars.items():
            print(f"export {key}=\"{value}\"")

def setup_prod_environment():
    """Set up production environment variables"""
    env_vars = {
        'FLASK_ENV': 'production',
        'FLASK_DEBUG': '0',
        'SECRET_KEY': generate_secure_key(48),  # Longer key for production
        'SERVER_API_KEY': generate_secure_key(48),
        'SESSION_COOKIE_SECURE': 'True',
        'REDIS_URL': input("\nEnter Redis URL for session storage (leave blank to skip): ") or None,
        # Add more variables as needed
    }
    
    # Remove None values
    env_vars = {k: v for k, v in env_vars.items() if v is not None}
    
    create_env_file(env_vars, '.env.production')
    
    print("\nProduction environment setup completed.")
    print("IMPORTANT: Make sure to copy these values to your hosting platform:")
    for key, value in env_vars.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up environment variables for Purrfect Platform")
    parser.add_argument('--env', choices=['dev', 'prod'], default='dev',
                        help='Environment to set up (dev or prod)')
    
    args = parser.parse_args()
    
    if args.env == 'dev':
        setup_dev_environment()
    else:
        setup_prod_environment()
    
    print("\nEnvironment setup complete!")