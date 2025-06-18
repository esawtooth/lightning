"""
Tests for the Lightning Planner CLI
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from lightning_core.planner.cli import (
    validate_plan_file, generate_mermaid_diagram, list_tools, list_events
)


class TestPlannerCLI:
    """Test CLI functionality"""
    
    def setup_method(self):
        """Setup for each test"""
        self.sample_plan = {
            "plan_name": "test_workflow",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.manual.trigger",
                    "kind": "manual",
                    "description": "Manual trigger"
                },
                {
                    "name": "event.task_complete"
                }
            ],
            "steps": [
                {
                    "name": "summarize_text",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Sample text to summarize",
                        "style": "brief"
                    },
                    "on": ["event.manual.trigger"],
                    "emits": ["event.task_complete"]
                }
            ]
        }
    
    def test_validate_plan_file_success(self):
        """Test successful plan validation"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_plan, f)
            temp_path = f.name
        
        try:
            # Should pass all validators now that petri_net is fixed
            result = validate_plan_file(temp_path, verbose=False)
            assert result is True  # All validators should pass
        finally:
            Path(temp_path).unlink()
    
    def test_validate_plan_file_not_found(self):
        """Test validation with non-existent file"""
        result = validate_plan_file("nonexistent_file.json", verbose=False)
        assert result is False
    
    def test_validate_plan_file_invalid_json(self):
        """Test validation with invalid JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name
        
        try:
            result = validate_plan_file(temp_path, verbose=False)
            assert result is False
        finally:
            Path(temp_path).unlink()
    
    def test_generate_mermaid_diagram_success(self):
        """Test successful Mermaid diagram generation"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_plan, f)
            plan_path = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_path = f.name
        
        try:
            result = generate_mermaid_diagram(plan_path, output_path, verbose=False)
            assert result is True
            
            # Check that output file was created and has content
            output_content = Path(output_path).read_text()
            assert "flowchart TD" in output_content
            assert "test_workflow" in output_content
            assert "event_manual_trigger" in output_content
            assert "summarize_text" in output_content
            
        finally:
            Path(plan_path).unlink()
            Path(output_path).unlink()
    
    def test_generate_mermaid_diagram_file_not_found(self):
        """Test Mermaid generation with non-existent file"""
        result = generate_mermaid_diagram("nonexistent.json", "output.md", verbose=False)
        assert result is False
    
    def test_generate_mermaid_diagram_invalid_json(self):
        """Test Mermaid generation with invalid JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json")
            temp_path = f.name
        
        try:
            result = generate_mermaid_diagram(temp_path, "output.md", verbose=False)
            assert result is False
        finally:
            Path(temp_path).unlink()
    
    def test_list_tools(self, capsys):
        """Test listing available tools"""
        result = list_tools(verbose=False)
        assert result is True
        
        captured = capsys.readouterr()
        assert "Available Tools" in captured.out
        assert "agent.conseil" in captured.out
        assert "llm.summarize" in captured.out
        assert "chat.sendTeamsMessage" in captured.out
    
    def test_list_events(self, capsys):
        """Test listing available events"""
        result = list_events(verbose=False)
        assert result is True
        
        captured = capsys.readouterr()
        assert "Available External Events" in captured.out
        assert "event.email.check" in captured.out
        assert "event.manual.trigger" in captured.out
    
    def test_mermaid_diagram_content_structure(self):
        """Test that generated Mermaid diagram has correct structure"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_plan, f)
            plan_path = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_path = f.name
        
        try:
            result = generate_mermaid_diagram(plan_path, output_path, verbose=False)
            assert result is True
            
            content = Path(output_path).read_text()
            lines = content.strip().split('\n')
            
            # Check structure
            assert lines[0] == "flowchart TD"
            assert any("test_workflow - acyclic workflow" in line for line in lines)
            
            # Check for external events with styling
            assert any("event_manual_trigger" in line and "manual" in line for line in lines)
            assert any("style event_manual_trigger fill:#e1f5fe" in line for line in lines)
            
            # Check for steps with styling
            assert any("summarize_text" in line and "llm.summarize" in line for line in lines)
            assert any("style summarize_text fill:#fff3e0" in line for line in lines)
            
            # Check for internal events with styling
            assert any("event_task_complete" in line for line in lines)
            assert any("style event_task_complete fill:#f3e5f5" in line for line in lines)
            
            # Check for connections
            assert any("event_manual_trigger --> summarize_text" in line for line in lines)
            assert any("summarize_text --> event_task_complete" in line for line in lines)
            
        finally:
            Path(plan_path).unlink()
            Path(output_path).unlink()
    
    def test_complex_plan_mermaid_generation(self):
        """Test Mermaid generation with a more complex plan"""
        complex_plan = {
            "plan_name": "complex_workflow",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.email.check",
                    "kind": "time.interval",
                    "schedule": "PT1H",
                    "description": "Check emails"
                },
                {
                    "name": "event.research_complete"
                },
                {
                    "name": "event.summary_ready"
                },
                {
                    "name": "event.notification_sent"
                }
            ],
            "steps": [
                {
                    "name": "conduct_research",
                    "action": "agent.conseil",
                    "args": {
                        "objective": "Research market trends",
                        "additional_context": "Focus on AI"
                    },
                    "on": ["event.email.check"],
                    "emits": ["event.research_complete"]
                },
                {
                    "name": "create_summary",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Research findings",
                        "style": "executive"
                    },
                    "on": ["event.research_complete"],
                    "emits": ["event.summary_ready"]
                },
                {
                    "name": "send_notification",
                    "action": "chat.sendTeamsMessage",
                    "args": {
                        "channel_id": "general",
                        "content": "Summary ready"
                    },
                    "on": ["event.summary_ready"],
                    "emits": ["event.notification_sent"]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(complex_plan, f)
            plan_path = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_path = f.name
        
        try:
            result = generate_mermaid_diagram(plan_path, output_path, verbose=False)
            assert result is True
            
            content = Path(output_path).read_text()
            
            # Check that all components are present
            assert "complex_workflow" in content
            assert "event_email_check" in content
            assert "conduct_research" in content
            assert "create_summary" in content
            assert "send_notification" in content
            
            # Check connections
            assert "event_email_check --> conduct_research" in content
            assert "conduct_research --> event_research_complete" in content
            assert "event_research_complete --> create_summary" in content
            assert "create_summary --> event_summary_ready" in content
            assert "event_summary_ready --> send_notification" in content
            assert "send_notification --> event_notification_sent" in content
            
        finally:
            Path(plan_path).unlink()
            Path(output_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
