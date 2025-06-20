"""
Simple integrated app entry point
"""
import os
import sys

# Add integrated_app to path
sys.path.insert(0, os.path.dirname(__file__))

# Import the app
from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)