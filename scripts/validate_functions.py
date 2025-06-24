#!/usr/bin/env python3
"""
Validate that all required Azure Functions are present before deployment.
This prevents missing function issues like the Auth function 404 error.
"""

import os
import sys
import json
from pathlib import Path

# List of required functions
REQUIRED_FUNCTIONS = [
    "Health",
    "PutEvent", 
    "UniversalEventProcessor",
    "Auth"  # OAuth authentication endpoint
]

def validate_function_exists(func_dir: Path, func_name: str) -> bool:
    """Check if a function exists with proper structure."""
    func_path = func_dir / func_name
    
    # Check directory exists
    if not func_path.is_dir():
        return False
    
    # Check __init__.py exists
    init_file = func_path / "__init__.py"
    if not init_file.exists():
        return False
    
    # Check function.json exists and is valid
    func_json = func_path / "function.json"
    if not func_json.exists():
        return False
    
    try:
        with open(func_json, 'r') as f:
            config = json.load(f)
            # Validate basic structure
            if 'bindings' not in config:
                print(f"  ❌ {func_name}/function.json missing 'bindings'")
                return False
            # scriptFile is optional - defaults to __init__.py
    except json.JSONDecodeError as e:
        print(f"  ❌ {func_name}/function.json is invalid JSON: {e}")
        return False
    
    return True

def main():
    """Validate all required functions exist."""
    # Find azure-function directory
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    func_dir = root_dir / "azure-function"
    
    if not func_dir.exists():
        print(f"❌ Azure Functions directory not found: {func_dir}")
        sys.exit(1)
    
    print(f"Validating Azure Functions in: {func_dir}")
    print("-" * 50)
    
    missing_functions = []
    invalid_functions = []
    
    for func_name in REQUIRED_FUNCTIONS:
        if not (func_dir / func_name).exists():
            missing_functions.append(func_name)
            print(f"❌ {func_name} - MISSING")
        elif not validate_function_exists(func_dir, func_name):
            invalid_functions.append(func_name)
            print(f"❌ {func_name} - INVALID STRUCTURE")
        else:
            print(f"✅ {func_name} - Valid")
    
    print("-" * 50)
    
    if missing_functions or invalid_functions:
        print("\n🚨 VALIDATION FAILED!")
        if missing_functions:
            print(f"\nMissing functions: {', '.join(missing_functions)}")
        if invalid_functions:
            print(f"\nInvalid functions: {', '.join(invalid_functions)}")
        print("\nPlease ensure all required functions are present before deployment.")
        sys.exit(1)
    else:
        print("\n✅ All required functions validated successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()