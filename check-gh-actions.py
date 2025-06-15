import runpy
import os

# Re-use implementation from scripts directory
globals().update(
    runpy.run_path(os.path.join(os.path.dirname(__file__), "scripts", "check-gh-actions.py"))
)
