"""
Comprehensive integration tests for the Lightning Planner
Tests the ability to generate valid plans using available tools
"""

import json
from unittest.mock import Mock, patch

import pytest

from lightning_core.planner.planner import call_planner_llm
from lightning_core.planner.registry import ToolRegistry
from lightning_core.planner.validator import run_validations_parallel, validate_plan_new


class TestPlannerIntegration:
    """Test planner's ability to generate valid plans using available tools"""

    def setup_method(self):
        """Setup for each test"""
        # Mock OpenAI responses for testing
        self.mock_openai_responses = {}

    def _mock_openai_response(self, plan_dict):
        """Helper to create mock OpenAI response"""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(plan_dict)
        return mock_response

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_01_simple_summarization_workflow(self, mock_client):
        """Test 1: Simple text summarization workflow"""
        expected_plan = {
            "plan_name": "document_summarization",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.manual.trigger",
                    "kind": "manual",
                    "description": "Manual trigger to start summarization",
                },
                {"name": "event.summary_complete"},
            ],
            "steps": [
                {
                    "name": "summarize_document",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Long document content here...",
                        "style": "executive",
                    },
                    "on": ["event.manual.trigger"],
                    "emits": ["event.summary_complete"],
                }
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a plan to summarize a document using executive style", {}
        )

        # Validate the generated plan
        validate_plan_new(result)
        assert result["plan_name"] == "document_summarization"
        assert len(result["steps"]) == 1
        assert result["steps"][0]["action"] == "llm.summarize"

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_02_agent_conseil_research_workflow(self, mock_client):
        """Test 2: Agent Conseil research and analysis workflow"""
        expected_plan = {
            "plan_name": "market_research_analysis",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.email.check",
                    "kind": "time.interval",
                    "schedule": "PT1H",
                    "description": "Check for research requests",
                },
                {"name": "event.research_complete"},
                {"name": "event.summary_ready"},
            ],
            "steps": [
                {
                    "name": "start_research",
                    "action": "agent.conseil",
                    "args": {
                        "objective": "Research market trends in AI technology",
                        "additional_context": "Focus on enterprise adoption rates",
                    },
                    "on": ["event.email.check"],
                    "emits": ["event.research_complete"],
                },
                {
                    "name": "summarize_findings",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Research findings from Conseil agent",
                        "style": "business",
                    },
                    "on": ["event.research_complete"],
                    "emits": ["event.summary_ready"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a workflow to research market trends using Conseil agent and summarize findings",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "market_research_analysis"
        assert len(result["steps"]) == 2
        assert any(step["action"] == "agent.conseil" for step in result["steps"])
        assert any(step["action"] == "llm.summarize" for step in result["steps"])

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_03_vex_agent_phone_call_workflow(self, mock_client):
        """Test 3: Vex agent phone call and follow-up workflow"""
        expected_plan = {
            "plan_name": "customer_outreach_campaign",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.calendar.sync",
                    "kind": "time.cron",
                    "schedule": "0 9 * * MON",
                    "description": "Weekly customer outreach",
                },
                {"name": "event.call_complete"},
                {"name": "event.teams_notification_sent"},
            ],
            "steps": [
                {
                    "name": "make_customer_call",
                    "action": "agent.vex",
                    "args": {
                        "objective": "Schedule product demo with customer",
                        "phone_number": "+1234567890",
                        "additional_context": "Customer expressed interest in our AI platform",
                    },
                    "on": ["event.calendar.sync"],
                    "emits": ["event.call_complete"],
                },
                {
                    "name": "notify_team",
                    "action": "chat.sendTeamsMessage",
                    "args": {
                        "channel_id": "sales-team",
                        "content": "Customer call completed - demo scheduled",
                    },
                    "on": ["event.call_complete"],
                    "emits": ["event.teams_notification_sent"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a workflow for weekly customer outreach calls using Vex agent with Teams notifications",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "customer_outreach_campaign"
        assert len(result["steps"]) == 2
        assert any(step["action"] == "agent.vex" for step in result["steps"])
        assert any(
            step["action"] == "chat.sendTeamsMessage" for step in result["steps"]
        )

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_04_scheduled_llm_analysis_workflow(self, mock_client):
        """Test 4: Scheduled LLM analysis with multiple models"""
        expected_plan = {
            "plan_name": "daily_report_generation",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.manual.trigger",
                    "kind": "manual",
                    "description": "Manual trigger to start daily report generation",
                },
                {"name": "event.scheduled_event"},
                {"name": "event.analysis_complete"},
                {"name": "event.llm.response"},
            ],
            "steps": [
                {
                    "name": "create_daily_schedule",
                    "action": "event.schedule.create",
                    "args": {
                        "title": "Daily Report Generation",
                        "cron": "0 8 * * *",
                        "start_time": "2024-01-01T08:00:00Z",
                        "end_time": "2024-12-31T08:00:00Z",
                    },
                    "on": ["event.manual.trigger"],
                    "emits": ["event.scheduled_event"],
                },
                {
                    "name": "analyze_with_gpt4",
                    "action": "llm.general_prompt",
                    "args": {
                        "system_prompt": "You are a business analyst",
                        "user_prompt": "Analyze yesterday's performance metrics",
                        "model": "gpt-4o",
                    },
                    "on": ["event.scheduled_event"],
                    "emits": ["event.analysis_complete"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a daily scheduled workflow for business analysis using GPT-4", {}
        )

        validate_plan_new(result)
        assert result["plan_name"] == "daily_report_generation"
        assert any(
            step["action"] == "event.schedule.create" for step in result["steps"]
        )
        assert any(step["action"] == "llm.general_prompt" for step in result["steps"])

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_05_timer_based_notification_workflow(self, mock_client):
        """Test 5: Timer-based workflow with notifications"""
        expected_plan = {
            "plan_name": "meeting_reminder_system",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.manual.trigger",
                    "kind": "manual",
                    "description": "Start meeting reminder",
                },
                {"name": "event.timed_event"},
                {"name": "event.reminder_sent"},
            ],
            "steps": [
                {
                    "name": "set_reminder_timer",
                    "action": "event.timer.start",
                    "args": {"duration": "900"},
                    "on": ["event.manual.trigger"],
                    "emits": ["event.timed_event"],
                },
                {
                    "name": "send_meeting_reminder",
                    "action": "chat.sendTeamsMessage",
                    "args": {
                        "channel_id": "general",
                        "content": "Meeting starts in 15 minutes!",
                    },
                    "on": ["event.timed_event"],
                    "emits": ["event.reminder_sent"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a meeting reminder system that sends Teams notification after 15 minutes",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "meeting_reminder_system"
        assert any(step["action"] == "event.timer.start" for step in result["steps"])
        assert any(
            step["action"] == "chat.sendTeamsMessage" for step in result["steps"]
        )

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_06_multi_agent_collaboration_workflow(self, mock_client):
        """Test 6: Multi-agent collaboration workflow"""
        expected_plan = {
            "plan_name": "research_and_outreach_pipeline",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.webhook.github",
                    "kind": "webhook",
                    "description": "GitHub webhook trigger",
                },
                {"name": "event.research_complete"},
                {"name": "event.call_scheduled"},
                {"name": "event.summary_ready"},
            ],
            "steps": [
                {
                    "name": "research_competitor",
                    "action": "agent.conseil",
                    "args": {
                        "objective": "Research competitor's new product launch",
                        "additional_context": "Focus on technical specifications and pricing",
                    },
                    "on": ["event.webhook.github"],
                    "emits": ["event.research_complete"],
                },
                {
                    "name": "schedule_stakeholder_call",
                    "action": "agent.vex",
                    "args": {
                        "objective": "Schedule urgent strategy meeting",
                        "phone_number": "+1987654321",
                        "additional_context": "Competitor launched similar product",
                    },
                    "on": ["event.research_complete"],
                    "emits": ["event.call_scheduled"],
                },
                {
                    "name": "create_executive_summary",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Competitor analysis and strategic implications",
                        "style": "executive",
                    },
                    "on": ["event.call_scheduled"],
                    "emits": ["event.summary_ready"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a workflow triggered by GitHub webhook that researches competitors, schedules calls, and creates summaries",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "research_and_outreach_pipeline"
        assert len(result["steps"]) == 3
        assert any(step["action"] == "agent.conseil" for step in result["steps"])
        assert any(step["action"] == "agent.vex" for step in result["steps"])
        assert any(step["action"] == "llm.summarize" for step in result["steps"])

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_07_reactive_monitoring_workflow(self, mock_client):
        """Test 7: Reactive monitoring and response workflow"""
        expected_plan = {
            "plan_name": "system_monitoring_response",
            "graph_type": "reactive",
            "events": [
                {
                    "name": "event.email.check",
                    "kind": "time.interval",
                    "schedule": "PT5M",
                    "description": "Monitor system alerts",
                },
                {"name": "event.alert_detected"},
                {"name": "event.analysis_complete"},
                {"name": "event.team_notified"},
            ],
            "steps": [
                {
                    "name": "analyze_alert",
                    "action": "llm.general_prompt",
                    "args": {
                        "system_prompt": "You are a system administrator",
                        "user_prompt": "Analyze this system alert and provide recommendations",
                        "model": "gpt-4o",
                    },
                    "on": ["event.email.check"],
                    "emits": ["event.analysis_complete"],
                },
                {
                    "name": "notify_oncall_team",
                    "action": "chat.sendTeamsMessage",
                    "args": {
                        "channel_id": "oncall-alerts",
                        "content": "System alert detected - analysis complete",
                    },
                    "on": ["event.analysis_complete"],
                    "emits": ["event.team_notified"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a reactive monitoring workflow that analyzes system alerts and notifies the team",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "system_monitoring_response"
        assert result["graph_type"] == "reactive"
        assert any(step["action"] == "llm.general_prompt" for step in result["steps"])
        assert any(
            step["action"] == "chat.sendTeamsMessage" for step in result["steps"]
        )

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_08_content_creation_pipeline(self, mock_client):
        """Test 8: Content creation and distribution pipeline"""
        expected_plan = {
            "plan_name": "weekly_content_pipeline",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.calendar.sync",
                    "kind": "time.cron",
                    "schedule": "0 10 * * FRI",
                    "description": "Weekly content creation",
                },
                {"name": "event.research_done"},
                {"name": "event.content_created"},
                {"name": "event.content_distributed"},
            ],
            "steps": [
                {
                    "name": "research_trending_topics",
                    "action": "agent.conseil",
                    "args": {
                        "objective": "Research trending topics in AI and technology",
                        "additional_context": "Focus on enterprise and business applications",
                    },
                    "on": ["event.calendar.sync"],
                    "emits": ["event.research_done"],
                },
                {
                    "name": "create_blog_content",
                    "action": "llm.general_prompt",
                    "args": {
                        "system_prompt": "You are a technical content writer",
                        "user_prompt": "Create a blog post about trending AI topics",
                        "model": "claude-sonnet-4",
                    },
                    "on": ["event.research_done"],
                    "emits": ["event.content_created"],
                },
                {
                    "name": "distribute_content",
                    "action": "chat.sendTeamsMessage",
                    "args": {
                        "channel_id": "marketing",
                        "content": "New blog post ready for review and publication",
                    },
                    "on": ["event.content_created"],
                    "emits": ["event.content_distributed"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a weekly content creation pipeline that researches topics, creates content, and notifies the marketing team",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "weekly_content_pipeline"
        assert len(result["steps"]) == 3
        assert any(step["action"] == "agent.conseil" for step in result["steps"])
        assert any(step["action"] == "llm.general_prompt" for step in result["steps"])
        assert any(
            step["action"] == "chat.sendTeamsMessage" for step in result["steps"]
        )

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_09_customer_feedback_analysis_workflow(self, mock_client):
        """Test 9: Customer feedback analysis and response workflow"""
        expected_plan = {
            "plan_name": "customer_feedback_processor",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.webhook.github",
                    "kind": "webhook",
                    "description": "Customer feedback webhook",
                },
                {"name": "event.feedback_analyzed"},
                {"name": "event.summary_created"},
                {"name": "event.followup_scheduled"},
            ],
            "steps": [
                {
                    "name": "analyze_feedback_sentiment",
                    "action": "llm.general_prompt",
                    "args": {
                        "system_prompt": "You are a customer success analyst",
                        "user_prompt": "Analyze customer feedback for sentiment and key issues",
                        "model": "gpt-4o",
                    },
                    "on": ["event.webhook.github"],
                    "emits": ["event.feedback_analyzed"],
                },
                {
                    "name": "create_feedback_summary",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Customer feedback analysis results",
                        "style": "actionable",
                    },
                    "on": ["event.feedback_analyzed"],
                    "emits": ["event.summary_created"],
                },
                {
                    "name": "schedule_customer_followup",
                    "action": "agent.vex",
                    "args": {
                        "objective": "Schedule follow-up call with customer",
                        "phone_number": "+1555123456",
                        "additional_context": "Address concerns raised in feedback",
                    },
                    "on": ["event.summary_created"],
                    "emits": ["event.followup_scheduled"],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a workflow to analyze customer feedback, create summaries, and schedule follow-up calls",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "customer_feedback_processor"
        assert len(result["steps"]) == 3
        assert any(step["action"] == "llm.general_prompt" for step in result["steps"])
        assert any(step["action"] == "llm.summarize" for step in result["steps"])
        assert any(step["action"] == "agent.vex" for step in result["steps"])

    @patch("lightning_core.planner.planner._get_openai_client")
    def test_10_complex_multi_stage_workflow(self, mock_client):
        """Test 10: Complex multi-stage workflow with all tool types"""
        expected_plan = {
            "plan_name": "comprehensive_business_intelligence",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.manual.trigger",
                    "kind": "manual",
                    "description": "Start comprehensive analysis",
                },
                {"name": "event.scheduled_event"},
                {"name": "event.research_phase_complete"},
                {"name": "event.analysis_complete"},
                {"name": "event.stakeholder_briefed"},
                {"name": "event.final_report_ready"},
            ],
            "steps": [
                {
                    "name": "schedule_weekly_analysis",
                    "action": "event.schedule.create",
                    "args": {
                        "title": "Weekly Business Intelligence",
                        "cron": "0 9 * * MON",
                        "start_time": "2024-01-01T09:00:00Z",
                        "end_time": "2024-12-31T09:00:00Z",
                    },
                    "on": ["event.manual.trigger"],
                    "emits": ["event.scheduled_event"],
                },
                {
                    "name": "conduct_market_research",
                    "action": "agent.conseil",
                    "args": {
                        "objective": "Comprehensive market analysis and competitor research",
                        "additional_context": "Include financial metrics, product launches, and strategic moves",
                    },
                    "on": ["event.scheduled_event"],
                    "emits": ["event.research_phase_complete"],
                },
                {
                    "name": "analyze_with_multiple_models",
                    "action": "llm.general_prompt",
                    "args": {
                        "system_prompt": "You are a senior business strategist",
                        "user_prompt": "Analyze market research data and provide strategic recommendations",
                        "model": "o3",
                    },
                    "on": ["event.research_phase_complete"],
                    "emits": ["event.analysis_complete"],
                },
                {
                    "name": "brief_stakeholders",
                    "action": "agent.vex",
                    "args": {
                        "objective": "Brief key stakeholders on analysis findings",
                        "phone_number": "+1800555000",
                        "additional_context": "Schedule executive briefing on strategic recommendations",
                    },
                    "on": ["event.analysis_complete"],
                    "emits": ["event.stakeholder_briefed"],
                },
                {
                    "name": "create_executive_report",
                    "action": "llm.summarize",
                    "args": {
                        "text": "Comprehensive business intelligence analysis and recommendations",
                        "style": "executive",
                    },
                    "on": ["event.stakeholder_briefed"],
                    "emits": ["event.final_report_ready"],
                },
                {
                    "name": "distribute_final_report",
                    "action": "chat.sendTeamsMessage",
                    "args": {
                        "channel_id": "executive-team",
                        "content": "Weekly business intelligence report is ready for review",
                    },
                    "on": ["event.final_report_ready"],
                    "emits": [],
                },
            ],
        }

        mock_client.return_value.chat.completions.create.return_value = (
            self._mock_openai_response(expected_plan)
        )

        result = call_planner_llm(
            "Create a comprehensive business intelligence workflow that schedules analysis, conducts research, analyzes data, briefs stakeholders, and distributes reports",
            {},
        )

        validate_plan_new(result)
        assert result["plan_name"] == "comprehensive_business_intelligence"
        assert len(result["steps"]) == 6

        # Verify all tool types are used
        actions_used = {step["action"] for step in result["steps"]}
        expected_actions = {
            "event.schedule.create",
            "agent.conseil",
            "llm.general_prompt",
            "agent.vex",
            "llm.summarize",
            "chat.sendTeamsMessage",
        }
        assert actions_used == expected_actions

    def test_tool_registry_completeness(self):
        """Verify all tools in registry are covered by tests"""
        tools = ToolRegistry.load()

        # Tools that should be covered by our tests
        expected_tools = {
            "agent.conseil",
            "agent.vex",
            "llm.summarize",
            "llm.general_prompt",
            "chat.sendTeamsMessage",
            "event.schedule.create",
            "event.timer.start",
            "cron.configure",
        }

        actual_tools = set(tools.keys())
        assert (
            actual_tools == expected_tools
        ), f"Tool registry mismatch: {actual_tools - expected_tools}"

    def test_event_registry_integration(self):
        """Verify event registry integration works correctly"""
        from lightning_core.events import EventRegistry

        # Verify external events are available
        external_events = EventRegistry.get_external_events()
        assert len(external_events) > 0

        # Verify specific external events exist
        expected_external = {
            "event.email.check",
            "event.calendar.sync",
            "event.webhook.github",
            "event.manual.trigger",
        }

        actual_external = set(external_events.keys())
        assert expected_external.issubset(
            actual_external
        ), f"Missing external events: {expected_external - actual_external}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
