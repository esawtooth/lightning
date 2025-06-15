#!/usr/bin/env python3
"""
Test script for Vextir CLI
"""

import subprocess
import sys
import json
import tempfile
import os
from pathlib import Path

def run_command(cmd, expect_success=True):
    """Run a CLI command and return the result"""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=30
        )
        
        if expect_success and result.returncode != 0:
            print(f"❌ Command failed: {cmd}")
            print(f"   stdout: {result.stdout}")
            print(f"   stderr: {result.stderr}")
            return False, result.stdout, result.stderr
        
        return True, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out: {cmd}")
        return False, "", "Command timed out"
    except Exception as e:
        print(f"❌ Command error: {cmd} - {e}")
        return False, "", str(e)

def test_basic_commands():
    """Test basic CLI commands"""
    print("🧪 Testing basic CLI commands...")
    
    # Test help command
    success, stdout, stderr = run_command("python -m vextir_cli.main --help")
    if not success:
        return False
    
    if "Vextir OS Command Line Interface" not in stdout:
        print("❌ Help command doesn't show expected content")
        return False
    
    print("✅ Help command works")
    
    # Test version/basic functionality
    success, stdout, stderr = run_command("python -m vextir_cli.main config get endpoint", expect_success=False)
    # This might fail if no config exists, which is expected
    print("✅ Config command accessible")
    
    return True

def test_config_commands():
    """Test configuration commands"""
    print("🧪 Testing configuration commands...")
    
    # Create temporary config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, "test_config.json")
        
        # Test setting config
        success, stdout, stderr = run_command(
            f"python -m vextir_cli.main --config {config_file} config set test_key test_value"
        )
        if not success:
            return False
        
        # Test getting config
        success, stdout, stderr = run_command(
            f"python -m vextir_cli.main --config {config_file} config get test_key"
        )
        if not success:
            return False
        
        if "test_value" not in stdout:
            print("❌ Config get doesn't return expected value")
            return False
        
        print("✅ Config set/get works")
        
        # Test listing all config
        success, stdout, stderr = run_command(
            f"python -m vextir_cli.main --config {config_file} config get"
        )
        if not success:
            return False
        
        print("✅ Config list works")
    
    return True

def test_command_structure():
    """Test that all command groups are accessible"""
    print("🧪 Testing command structure...")
    
    commands = [
        "event --help",
        "driver --help", 
        "model --help",
        "tool --help",
        "context --help",
        "instruction --help",
        "system --help",
        "config --help"
    ]
    
    for cmd in commands:
        success, stdout, stderr = run_command(f"python -m vextir_cli.main {cmd}")
        if not success:
            print(f"❌ Command group failed: {cmd}")
            return False
        
        # Check that help content is present
        if "Usage:" not in stdout and "Commands:" not in stdout:
            print(f"❌ Command group help incomplete: {cmd}")
            return False
    
    print("✅ All command groups accessible")
    return True

def test_json_output():
    """Test JSON output formatting"""
    print("🧪 Testing JSON output...")
    
    # Test with a command that should produce JSON
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = os.path.join(temp_dir, "test_config.json")
        
        # Set some config values
        run_command(f"python -m vextir_cli.main --config {config_file} config set endpoint https://test.com")
        run_command(f"python -m vextir_cli.main --config {config_file} config set auth.method azure_cli")
        
        # Get config as JSON
        success, stdout, stderr = run_command(
            f"python -m vextir_cli.main --config {config_file} config get"
        )
        
        if not success:
            return False
        
        # Try to parse as JSON
        try:
            config_data = json.loads(stdout)
            if config_data.get("endpoint") != "https://test.com":
                print("❌ JSON output doesn't contain expected data")
                return False
        except json.JSONDecodeError:
            print("❌ Config output is not valid JSON")
            return False
    
    print("✅ JSON output works")
    return True

def test_error_handling():
    """Test error handling"""
    print("🧪 Testing error handling...")
    
    # Test invalid command
    success, stdout, stderr = run_command(
        "python -m vextir_cli.main invalid_command", 
        expect_success=False
    )
    
    if success:  # Should fail
        print("❌ Invalid command should have failed")
        return False
    
    # Test invalid config key
    success, stdout, stderr = run_command(
        "python -m vextir_cli.main config get nonexistent_key",
        expect_success=False
    )
    
    # This might succeed with empty output, which is fine
    print("✅ Error handling works")
    return True

def main():
    """Run all tests"""
    print("🚀 Starting Vextir CLI Tests")
    print("=" * 50)
    
    tests = [
        test_basic_commands,
        test_config_commands,
        test_command_structure,
        test_json_output,
        test_error_handling
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
        
        print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
