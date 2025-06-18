#!/usr/bin/env python3
"""
Script to trigger a new deployment with enhanced container logging.
This will help us diagnose the 502 error by getting better visibility into container startup failures.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    print(result.stdout)
    return True

def main():
    """Main function to trigger deployment with enhanced logging."""
    
    # Check if we're in the right directory
    if not Path("infra/__main__.py").exists():
        print("Error: Please run this script from the project root directory")
        sys.exit(1)
    
    print("🔧 Triggering deployment with enhanced container logging...")
    
    # Commit the changes
    print("\n📝 Committing logging improvements...")
    if not run_command(["git", "add", "infra/__main__.py", "ui/chat_client/start.sh"]):
        print("Failed to add files to git")
        sys.exit(1)
    
    if not run_command(["git", "commit", "-m", "feat: enhance container logging and debugging for 502 error diagnosis"]):
        print("Failed to commit changes")
        sys.exit(1)
    
    # Push to trigger GitHub Actions
    print("\n🚀 Pushing to trigger GitHub Actions deployment...")
    if not run_command(["git", "push", "origin", "main"]):
        print("Failed to push to GitHub")
        sys.exit(1)
    
    print("\n✅ Deployment triggered successfully!")
    print("\n📊 Enhanced logging features added:")
    print("  • Better restart policy (ON_FAILURE instead of ALWAYS)")
    print("  • Health and readiness probes for UI container")
    print("  • Enhanced Log Analytics with Container Insights")
    print("  • Debug environment variables (PYTHONUNBUFFERED, LOG_LEVEL, etc.)")
    print("  • Comprehensive startup script with file/import checks")
    print("  • Detailed uvicorn logging")
    
    print("\n🔍 After deployment, you can check logs with:")
    print("  az container logs --resource-group vextir-dev --name chatui")
    print("  az container show --resource-group vextir-dev --name chatui --query 'containers[0].instanceView'")
    
    print("\n📈 You can also check Log Analytics in Azure Portal for detailed container insights")

if __name__ == "__main__":
    main()
