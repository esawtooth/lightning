"""
Direct plan validation tests for the Lightning Planner
Tests plan validation using the new validator system without LLM calls
"""

import pytest

from lightning_core.events import EventRegistry
from lightning_core.planner.registry import ToolRegistry
from lightning_core.planner.validator import run_validations_parallel, validate_plan_new


class TestPlanValidation:
    """Test plan validation with various workflow scenarios"""

    def test_01_simple_summarization_plan_validation(self):
        """Test 1: Validate simple text summarization plan"""
        plan = {
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

        # Test individual validators (excluding problematic Petri net)
        results = run_validations_parallel(plan)

        # Check that most validators pass
        passed_validators = [r for r in results if r.success]
        failed_validators = [r for r in results if not r.success]

        print(f"Passed validators: {[r.validator_name for r in passed_validators]}")
        print(
            f"Failed validators: {[r.validator_name + ': ' + r.error_message for r in failed_validators]}"
        )

        # Should pass JSON schema, external events, tools, and pydantic
        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(
            actual_passing
        ), f"Expected validators failed: {expected_passing - actual_passing}"

        # Verify plan structure
        assert plan["plan_name"] == "document_summarization"
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["action"] == "llm.summarize"

    def test_02_agent_conseil_research_plan_validation(self):
        """Test 2: Validate Agent Conseil research workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        # Should pass core validators
        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert len(plan["steps"]) == 2
        assert any(step["action"] == "agent.conseil" for step in plan["steps"])
        assert any(step["action"] == "llm.summarize" for step in plan["steps"])

    def test_03_vex_agent_phone_call_plan_validation(self):
        """Test 3: Validate Vex agent phone call workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert len(plan["steps"]) == 2
        assert any(step["action"] == "agent.vex" for step in plan["steps"])
        assert any(step["action"] == "chat.sendTeamsMessage" for step in plan["steps"])

    def test_04_scheduled_llm_analysis_plan_validation(self):
        """Test 4: Validate scheduled LLM analysis workflow plan"""
        plan = {
            "plan_name": "daily_report_generation",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.manual.trigger",
                    "kind": "manual",
                    "description": "Start daily report",
                },
                {"name": "event.scheduled_event"},
                {"name": "event.analysis_complete"},
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert any(step["action"] == "event.schedule.create" for step in plan["steps"])
        assert any(step["action"] == "llm.general_prompt" for step in plan["steps"])

    def test_05_timer_based_notification_plan_validation(self):
        """Test 5: Validate timer-based workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert any(step["action"] == "event.timer.start" for step in plan["steps"])
        assert any(step["action"] == "chat.sendTeamsMessage" for step in plan["steps"])

    def test_06_multi_agent_collaboration_plan_validation(self):
        """Test 6: Validate multi-agent collaboration workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert len(plan["steps"]) == 3
        assert any(step["action"] == "agent.conseil" for step in plan["steps"])
        assert any(step["action"] == "agent.vex" for step in plan["steps"])
        assert any(step["action"] == "llm.summarize" for step in plan["steps"])

    def test_07_reactive_monitoring_plan_validation(self):
        """Test 7: Validate reactive monitoring workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert plan["graph_type"] == "reactive"
        assert any(step["action"] == "llm.general_prompt" for step in plan["steps"])
        assert any(step["action"] == "chat.sendTeamsMessage" for step in plan["steps"])

    def test_08_content_creation_pipeline_validation(self):
        """Test 8: Validate content creation pipeline plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert len(plan["steps"]) == 3
        assert any(step["action"] == "agent.conseil" for step in plan["steps"])
        assert any(step["action"] == "llm.general_prompt" for step in plan["steps"])
        assert any(step["action"] == "chat.sendTeamsMessage" for step in plan["steps"])

    def test_09_customer_feedback_analysis_plan_validation(self):
        """Test 9: Validate customer feedback analysis workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert len(plan["steps"]) == 3
        assert any(step["action"] == "llm.general_prompt" for step in plan["steps"])
        assert any(step["action"] == "llm.summarize" for step in plan["steps"])
        assert any(step["action"] == "agent.vex" for step in plan["steps"])

    def test_10_complex_multi_stage_plan_validation(self):
        """Test 10: Validate complex multi-stage workflow plan"""
        plan = {
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

        results = run_validations_parallel(plan)
        passed_validators = [r for r in results if r.success]

        expected_passing = {"json_schema", "external_events", "tools", "pydantic"}
        actual_passing = {r.validator_name for r in passed_validators}

        assert expected_passing.issubset(actual_passing)
        assert len(plan["steps"]) == 6

        # Verify all tool types are used
        actions_used = {step["action"] for step in plan["steps"]}
        expected_actions = {
            "event.schedule.create",
            "agent.conseil",
            "llm.general_prompt",
            "agent.vex",
            "llm.summarize",
            "chat.sendTeamsMessage",
        }
        assert actions_used == expected_actions

    def test_validation_error_scenarios(self):
        """Test validation error scenarios"""

        # Test invalid tool
        invalid_tool_plan = {
            "plan_name": "invalid_tool_test",
            "graph_type": "acyclic",
            "events": [{"name": "event.manual.trigger", "kind": "manual"}],
            "steps": [
                {
                    "name": "invalid_step",
                    "action": "nonexistent.tool",
                    "args": {},
                    "on": ["event.manual.trigger"],
                    "emits": [],
                }
            ],
        }

        results = run_validations_parallel(invalid_tool_plan)
        tool_validator_result = next(
            (r for r in results if r.validator_name == "tools"), None
        )
        assert tool_validator_result is not None
        assert not tool_validator_result.success
        assert "nonexistent.tool" in tool_validator_result.error_message

        # Test missing required args
        missing_args_plan = {
            "plan_name": "missing_args_test",
            "graph_type": "acyclic",
            "events": [{"name": "event.manual.trigger", "kind": "manual"}],
            "steps": [
                {
                    "name": "missing_args_step",
                    "action": "llm.summarize",
                    "args": {"text": "some text"},  # missing 'style'
                    "on": ["event.manual.trigger"],
                    "emits": [],
                }
            ],
        }

        results = run_validations_parallel(missing_args_plan)
        tool_validator_result = next(
            (r for r in results if r.validator_name == "tools"), None
        )
        assert tool_validator_result is not None
        assert not tool_validator_result.success
        assert "missing required arguments" in tool_validator_result.error_message

    def test_external_event_validation(self):
        """Test external event validation scenarios"""

        # Test valid external event
        valid_external_plan = {
            "plan_name": "valid_external_test",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.email.check",
                    "kind": "time.interval",
                    "schedule": "PT5M",
                    "description": "Check emails",
                }
            ],
            "steps": [
                {
                    "name": "test_step",
                    "action": "llm.summarize",
                    "args": {"text": "test", "style": "brief"},
                    "on": ["event.email.check"],
                    "emits": [],
                }
            ],
        }

        results = run_validations_parallel(valid_external_plan)
        external_validator_result = next(
            (r for r in results if r.validator_name == "external_events"), None
        )
        assert external_validator_result is not None
        assert external_validator_result.success

        # Test invalid external event kind
        invalid_external_plan = {
            "plan_name": "invalid_external_test",
            "graph_type": "acyclic",
            "events": [
                {
                    "name": "event.email.check",
                    "kind": "wrong_kind",  # Should be "time.interval"
                    "schedule": "PT5M",
                }
            ],
            "steps": [
                {
                    "name": "test_step",
                    "action": "llm.summarize",
                    "args": {"text": "test", "style": "brief"},
                    "on": ["event.email.check"],
                    "emits": [],
                }
            ],
        }

        results = run_validations_parallel(invalid_external_plan)
        external_validator_result = next(
            (r for r in results if r.validator_name == "external_events"), None
        )
        assert external_validator_result is not None
        assert not external_validator_result.success
        assert "Kind mismatch" in external_validator_result.error_message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
