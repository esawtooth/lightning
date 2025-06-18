"""Tests for planner schema module"""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from lightning_core.planner.schema import (
    EmailArgs,
    EventModel,
    ExternalEventModel,
    PlanModel,
    StepModel,
    SummarizeArgs,
    ToolRef,
    dump_schema,
)


class TestExternalEventModel:
    """Test ExternalEventModel validation"""

    def test_valid_external_event(self):
        """Test creating a valid external event"""
        event = ExternalEventModel(
            name="event.daily_check",
            kind="time.cron",
            schedule="0 9 * * *",
            description="Daily morning check",
        )
        assert event.name == "event.daily_check"
        assert event.kind == "time.cron"
        assert event.schedule == "0 9 * * *"
        assert event.description == "Daily morning check"

    def test_invalid_event_name(self):
        """Test that event name must start with 'event.'"""
        with pytest.raises(ValidationError):
            ExternalEventModel(name="invalid_name", kind="time.cron")

    def test_invalid_event_kind(self):
        """Test that event kind must be valid"""
        with pytest.raises(ValidationError):
            ExternalEventModel(name="event.test", kind="invalid_kind")

    def test_minimal_external_event(self):
        """Test creating minimal external event"""
        event = ExternalEventModel(name="event.webhook", kind="webhook")
        assert event.name == "event.webhook"
        assert event.kind == "webhook"
        assert event.schedule is None
        assert event.description is None


class TestStepModel:
    """Test StepModel validation"""

    def test_valid_step(self):
        """Test creating a valid step"""
        step = StepModel(
            name="send_email",
            on=["event.daily_check"],
            action="email.send",
            args={"to": "user@example.com", "subject": "Daily Report"},
            emits=["event.email_sent"],
            guard="user.active == true",
        )
        assert step.name == "send_email"
        assert step.on == ["event.daily_check"]
        assert step.action == "email.send"
        assert step.args == {"to": "user@example.com", "subject": "Daily Report"}
        assert step.emits == ["event.email_sent"]
        assert step.guard == "user.active == true"

    def test_minimal_step(self):
        """Test creating minimal step"""
        step = StepModel(
            name="simple_step", on=["event.trigger"], action="simple.action"
        )
        assert step.name == "simple_step"
        assert step.on == ["event.trigger"]
        assert step.action == "simple.action"
        assert step.args == {}
        assert step.emits == []
        assert step.guard is None

    def test_empty_name_invalid(self):
        """Test that empty step name is invalid"""
        with pytest.raises(ValidationError):
            StepModel(name="", on=["event.trigger"], action="simple.action")


class TestPlanModel:
    """Test PlanModel validation"""

    def test_valid_plan(self):
        """Test creating a valid plan"""
        events = [
            ExternalEventModel(
                name="event.daily", kind="time.cron", schedule="0 9 * * *"
            )
        ]
        steps = [StepModel(name="step1", on=["event.daily"], action="test.action")]

        plan = PlanModel(
            plan_name="test_plan", graph_type="acyclic", events=events, steps=steps
        )

        assert plan.plan_name == "test_plan"
        assert plan.graph_type == "acyclic"
        assert len(plan.events) == 1
        assert len(plan.steps) == 1

    def test_reactive_plan(self):
        """Test creating a reactive plan"""
        events = [ExternalEventModel(name="event.webhook", kind="webhook")]
        steps = [
            StepModel(
                name="step1",
                on=["event.webhook"],
                action="process.webhook",
                emits=["event.processed"],
            ),
            StepModel(name="step2", on=["event.processed"], action="notify.user"),
        ]

        plan = PlanModel(
            plan_name="reactive_plan", graph_type="reactive", events=events, steps=steps
        )

        assert plan.graph_type == "reactive"
        assert len(plan.steps) == 2

    def test_invalid_graph_type(self):
        """Test that invalid graph type is rejected"""
        with pytest.raises(ValidationError):
            PlanModel(
                plan_name="test_plan", graph_type="invalid_type", events=[], steps=[]
            )

    def test_empty_plan_name_invalid(self):
        """Test that empty plan name is invalid"""
        with pytest.raises(ValidationError):
            PlanModel(plan_name="", graph_type="acyclic", events=[], steps=[])


class TestToolRef:
    """Test ToolRef validation"""

    def test_valid_tool_ref(self):
        """Test creating a valid tool reference"""
        tool_ref = ToolRef(
            action="email.send", args={"to": "user@example.com", "subject": "Test"}
        )
        assert tool_ref.action == "email.send"
        assert tool_ref.args == {"to": "user@example.com", "subject": "Test"}

    def test_minimal_tool_ref(self):
        """Test creating minimal tool reference"""
        tool_ref = ToolRef(action="simple.action")
        assert tool_ref.action == "simple.action"
        assert tool_ref.args == {}

    def test_empty_action_invalid(self):
        """Test that empty action is invalid"""
        with pytest.raises(ValidationError):
            ToolRef(action="")


class TestArgsModels:
    """Test argument models"""

    def test_email_args(self):
        """Test EmailArgs model"""
        args = EmailArgs(folder="inbox", since="2023-01-01T00:00:00Z")
        assert args.folder == "inbox"
        assert args.since == "2023-01-01T00:00:00Z"

    def test_summarize_args(self):
        """Test SummarizeArgs model"""
        args = SummarizeArgs(
            text="This is a long text to summarize", style="bullet_points"
        )
        assert args.text == "This is a long text to summarize"
        assert args.style == "bullet_points"


class TestSchemaUtils:
    """Test schema utility functions"""

    def test_dump_schema(self):
        """Test schema dumping functionality"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            dump_schema(schema_path)

            assert schema_path.exists()

            # Verify the schema is valid JSON
            with open(schema_path) as f:
                schema_data = json.load(f)

            assert isinstance(schema_data, dict)
            assert "properties" in schema_data
            assert "plan_name" in schema_data["properties"]
            assert "graph_type" in schema_data["properties"]
            assert "events" in schema_data["properties"]
            assert "steps" in schema_data["properties"]


class TestComplexPlan:
    """Test complex plan scenarios"""

    def test_email_workflow_plan(self):
        """Test a realistic email workflow plan"""
        events = [
            ExternalEventModel(
                name="event.daily_summary",
                kind="time.cron",
                schedule="0 18 * * MON-FRI",
                description="Daily summary at 6 PM on weekdays",
            ),
            ExternalEventModel(
                name="event.urgent_email",
                kind="webhook",
                description="Urgent email received",
            ),
        ]

        steps = [
            StepModel(
                name="fetch_emails",
                on=["event.daily_summary"],
                action="email.fetch",
                args={"folder": "inbox", "since": "today"},
                emits=["event.emails_fetched"],
            ),
            StepModel(
                name="summarize_emails",
                on=["event.emails_fetched"],
                action="text.summarize",
                args={"style": "bullet_points"},
                emits=["event.summary_ready"],
            ),
            StepModel(
                name="send_summary",
                on=["event.summary_ready"],
                action="email.send",
                args={"to": "manager@company.com", "subject": "Daily Email Summary"},
            ),
            StepModel(
                name="handle_urgent",
                on=["event.urgent_email"],
                action="notification.send",
                args={"channel": "slack", "urgency": "high"},
                guard="email.priority == 'urgent'",
            ),
        ]

        plan = PlanModel(
            plan_name="email_workflow",
            graph_type="reactive",
            events=events,
            steps=steps,
        )

        assert plan.plan_name == "email_workflow"
        assert len(plan.events) == 2
        assert len(plan.steps) == 4

        # Verify event names
        event_names = [event.name for event in plan.events]
        assert "event.daily_summary" in event_names
        assert "event.urgent_email" in event_names

        # Verify step dependencies
        step_triggers = {}
        for step in plan.steps:
            step_triggers[step.name] = step.on

        assert "event.daily_summary" in step_triggers["fetch_emails"]
        assert "event.emails_fetched" in step_triggers["summarize_emails"]
        assert "event.summary_ready" in step_triggers["send_summary"]
        assert "event.urgent_email" in step_triggers["handle_urgent"]
