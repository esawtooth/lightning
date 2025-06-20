#!/usr/bin/env python3
"""
Runner script for the integrated app
"""
import os
import sys

# Add current directory to Python path so imports work
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/integrated_app')

# Change to the integrated_app directory for relative imports
os.chdir('/app/integrated_app')

# Now import the app directly
from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8080,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )