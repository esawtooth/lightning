"""
Lightning Planner CLI - Command-line interface for plan generation and visualization
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ..events import EventRegistry
from .planner import call_planner_llm
from .registry import ToolRegistry
from .validator import PlanValidationError, run_validations_parallel, validate_plan_new


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def call_planner_llm_with_debug(
    instruction: str, registry_subset: Dict[str, Any], verbose: bool = False
) -> Dict[str, Any]:
    """Enhanced planner with detailed debugging output"""
    import time

    from openai import OpenAI

    logger = logging.getLogger(__name__)

    # Get OpenAI client
    client = OpenAI()

    # Build system prompt (same as original)
    from .planner import _make_system_prompt

    system_prompt = _make_system_prompt()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]

    max_retries = 4
    seconds_between = 0.8

    for attempt in range(1, max_retries + 1):
        logger.info(f"🔄 Attempt {attempt}/{max_retries}")

        try:
            # Call OpenAI
            resp = client.chat.completions.create(
                model="o3", messages=messages, response_format={"type": "json_object"}
            )

            plan_json = json.loads(resp.choices[0].message.content)

            # Show generated plan
            logger.info(f"📋 Generated plan attempt {attempt}:")
            logger.info(f"   Plan name: {plan_json.get('plan_name', 'MISSING')}")
            logger.info(f"   Graph type: {plan_json.get('graph_type', 'MISSING')}")
            logger.info(f"   Events: {len(plan_json.get('events', []))}")
            logger.info(f"   Steps: {len(plan_json.get('steps', []))}")

            if verbose:
                logger.debug("📄 Full generated plan:")
                logger.debug(json.dumps(plan_json, indent=2))

            # Validate the plan
            logger.info("🔍 Validating generated plan...")
            results = run_validations_parallel(plan_json)

            passed_validators = [r for r in results if r.success]
            failed_validators = [r for r in results if not r.success]

            logger.info(
                f"   Validation results: {len(passed_validators)}/{len(results)} passed"
            )

            for result in passed_validators:
                logger.info(f"   ✅ {result.validator_name}: PASS")

            for result in failed_validators:
                logger.warning(f"   ❌ {result.validator_name}: {result.error_message}")

            if len(failed_validators) == 0:
                logger.info("🎉 Plan validation successful!")
                return plan_json
            else:
                # Add validation feedback to conversation
                error_summary = "\n".join(
                    [
                        f"- {r.validator_name}: {r.error_message}"
                        for r in failed_validators
                    ]
                )
                feedback_message = f"VALIDATION FAILED:\n{error_summary}\n\nPlease fix these issues and generate a corrected plan."

                messages.append({"role": "system", "content": feedback_message})

                logger.warning(f"❌ Attempt {attempt} failed validation, retrying...")

        except json.JSONDecodeError as e:
            logger.error(f"❌ Attempt {attempt} failed: Invalid JSON response - {e}")
            messages.append(
                {
                    "role": "system",
                    "content": f"ERROR: Your response was not valid JSON. Please return only a valid JSON object. Error: {e}",
                }
            )
        except Exception as e:
            logger.error(f"❌ Attempt {attempt} failed: {e}")
            messages.append(
                {
                    "role": "system",
                    "content": f"ERROR: {e}\nPlease generate a corrected plan.",
                }
            )

        if attempt < max_retries:
            logger.info(f"⏳ Waiting {seconds_between}s before retry...")
            time.sleep(seconds_between)

    # If we get here, all attempts failed
    logger.error(f"💥 Failed to generate valid plan after {max_retries} attempts")

    # Show available constraints to help debug
    logger.error("🔧 Available tools:")
    tools = ToolRegistry.load()
    for name in tools.keys():
        logger.error(f"   - {name}")

    logger.error("📅 Available external events:")
    from ..events import EventRegistry

    external_events = EventRegistry.get_external_events()
    for name, event_def in external_events.items():
        logger.error(f"   - {name} ({event_def.kind})")

    raise RuntimeError(
        f"Planner could not produce a valid plan in {max_retries} attempts."
    )


def generate_plan(
    instruction: str, output_file: Optional[str] = None, verbose: bool = False
) -> Dict[str, Any]:
    """Generate a plan from instruction"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    logger.info(f"Generating plan for instruction: {instruction}")

    try:
        # Generate plan using LLM with enhanced debugging
        plan = call_planner_llm_with_debug(instruction, {}, verbose=verbose)

        logger.info(f"✅ Successfully generated plan: {plan['plan_name']}")
        logger.info(f"Plan type: {plan['graph_type']}")
        logger.info(f"Events: {len(plan['events'])}")
        logger.info(f"Steps: {len(plan['steps'])}")

        # Save to file if specified
        if output_file:
            output_path = Path(output_file)
            output_path.write_text(json.dumps(plan, indent=2))
            logger.info(f"Plan saved to: {output_path}")

        return plan

    except Exception as e:
        logger.error(f"Failed to generate plan: {e}")
        raise


def validate_plan_file(plan_file: str, verbose: bool = False) -> bool:
    """Validate a plan from file"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        # Load plan from file
        plan_path = Path(plan_file)
        if not plan_path.exists():
            logger.error(f"Plan file not found: {plan_file}")
            return False

        plan = json.loads(plan_path.read_text())
        logger.info(f"Loaded plan: {plan['plan_name']}")

        # Run validation
        results = run_validations_parallel(plan)

        # Report results
        passed_validators = [r for r in results if r.success]
        failed_validators = [r for r in results if not r.success]

        logger.info(f"Validation Results:")
        logger.info(f"  Passed: {len(passed_validators)}/{len(results)}")

        for result in passed_validators:
            logger.info(f"  ✓ {result.validator_name}: PASS")

        for result in failed_validators:
            logger.error(f"  ✗ {result.validator_name}: {result.error_message}")

        success = len(failed_validators) == 0
        if success:
            logger.info("✅ Plan validation PASSED")
        else:
            logger.error("❌ Plan validation FAILED")

        return success

    except Exception as e:
        logger.error(f"Failed to validate plan: {e}")
        return False


def visualize_plan(
    plan_file: str,
    output_file: Optional[str] = None,
    format: str = "png",
    verbose: bool = False,
):
    """Generate visual representation of a plan"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        # Import visualization dependencies
        try:
            import graphviz
        except ImportError:
            logger.error("Graphviz not installed. Install with: pip install graphviz")
            return False

        # Load plan
        plan_path = Path(plan_file)
        if not plan_path.exists():
            logger.error(f"Plan file not found: {plan_file}")
            return False

        plan = json.loads(plan_path.read_text())
        logger.info(f"Visualizing plan: {plan['plan_name']}")

        # Create graph
        dot = graphviz.Digraph(comment=plan["plan_name"])
        dot.attr(rankdir="TB", size="12,8")
        dot.attr("node", shape="box", style="rounded,filled")

        # Add events as nodes
        event_colors = {
            "external": "#e1f5fe",  # Light blue for external events
            "internal": "#f3e5f5",  # Light purple for internal events
        }

        external_events = {evt["name"] for evt in plan["events"] if evt.get("kind")}

        for event in plan["events"]:
            name = event["name"]
            color = (
                event_colors["external"]
                if name in external_events
                else event_colors["internal"]
            )

            label = name
            if event.get("kind"):
                label += f"\\n({event['kind']})"
            if event.get("schedule"):
                label += f"\\n{event['schedule']}"

            dot.node(name, label, fillcolor=color)

        # Add internal events that are emitted by steps
        for step in plan["steps"]:
            for emitted_event in step.get("emits", []):
                if emitted_event not in [evt["name"] for evt in plan["events"]]:
                    dot.node(
                        emitted_event, emitted_event, fillcolor=event_colors["internal"]
                    )

        # Add steps as nodes
        for step in plan["steps"]:
            step_name = step["name"]
            action = step["action"]

            label = f"{step_name}\\n[{action}]"

            # Add key arguments to label
            if step.get("args"):
                key_args = []
                for key, value in step["args"].items():
                    if len(str(value)) < 20:  # Only show short values
                        key_args.append(f"{key}: {value}")
                if key_args:
                    label += "\\n" + "\\n".join(key_args[:2])  # Max 2 args

            dot.node(
                step_name, label, fillcolor="#fff3e0", shape="box"
            )  # Light orange for steps

        # Add edges from events to steps (triggers)
        for step in plan["steps"]:
            step_name = step["name"]
            for trigger_event in step["on"]:
                dot.edge(trigger_event, step_name, color="blue")

        # Add edges from steps to emitted events
        for step in plan["steps"]:
            step_name = step["name"]
            for emitted_event in step.get("emits", []):
                dot.edge(step_name, emitted_event, color="green")

        # Set output file
        if not output_file:
            output_file = f"{plan['plan_name']}_visualization"

        # Render graph
        output_path = Path(output_file)
        dot.render(str(output_path), format=format, cleanup=True)

        final_path = output_path.with_suffix(f".{format}")
        logger.info(f"Visualization saved to: {final_path}")

        return True

    except Exception as e:
        logger.error(f"Failed to visualize plan: {e}")
        return False


def generate_mermaid_diagram(
    plan_file: str, output_file: Optional[str] = None, verbose: bool = False
):
    """Generate Mermaid diagram representation of a plan"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        # Load plan
        plan_path = Path(plan_file)
        if not plan_path.exists():
            logger.error(f"Plan file not found: {plan_file}")
            return False

        plan = json.loads(plan_path.read_text())
        logger.info(f"Generating Mermaid diagram for: {plan['plan_name']}")

        # Generate Mermaid flowchart
        mermaid_lines = [
            f"flowchart TD",
            f"    %% {plan['plan_name']} - {plan['graph_type']} workflow",
            "",
        ]

        # Add external events
        external_events = {evt["name"] for evt in plan["events"] if evt.get("kind")}
        for event in plan["events"]:
            if event["name"] in external_events:
                kind = event.get("kind", "external")
                schedule = event.get("schedule", "")
                label = f"{event['name']}\\n({kind})"
                if schedule:
                    label += f"\\n{schedule}"

                node_id = event["name"].replace(".", "_").replace("-", "_")
                mermaid_lines.append(f'    {node_id}["{label}"]')
                mermaid_lines.append(f"    style {node_id} fill:#e1f5fe")

        mermaid_lines.append("")

        # Add steps
        for step in plan["steps"]:
            step_id = step["name"].replace(".", "_").replace("-", "_")
            action = step["action"]
            label = f"{step['name']}\\n[{action}]"

            mermaid_lines.append(f'    {step_id}["{label}"]')
            mermaid_lines.append(f"    style {step_id} fill:#fff3e0")

        mermaid_lines.append("")

        # Add internal events
        all_internal_events = set()
        for step in plan["steps"]:
            all_internal_events.update(step.get("emits", []))

        # Remove external events from internal events
        internal_events = all_internal_events - external_events
        for event_name in internal_events:
            event_id = event_name.replace(".", "_").replace("-", "_")
            mermaid_lines.append(f'    {event_id}["{event_name}"]')
            mermaid_lines.append(f"    style {event_id} fill:#f3e5f5")

        mermaid_lines.append("")

        # Add connections
        for step in plan["steps"]:
            step_id = step["name"].replace(".", "_").replace("-", "_")

            # Trigger connections (events -> steps)
            for trigger_event in step["on"]:
                trigger_id = trigger_event.replace(".", "_").replace("-", "_")
                mermaid_lines.append(f"    {trigger_id} --> {step_id}")

            # Emit connections (steps -> events)
            for emitted_event in step.get("emits", []):
                emit_id = emitted_event.replace(".", "_").replace("-", "_")
                mermaid_lines.append(f"    {step_id} --> {emit_id}")

        # Join all lines
        mermaid_content = "\n".join(mermaid_lines)

        # Save to file
        if not output_file:
            output_file = f"{plan['plan_name']}_mermaid.md"

        output_path = Path(output_file)
        output_path.write_text(mermaid_content)

        logger.info(f"Mermaid diagram saved to: {output_path}")
        logger.info("You can visualize this at: https://mermaid.live/")

        return True

    except Exception as e:
        logger.error(f"Failed to generate Mermaid diagram: {e}")
        return False


def list_tools(verbose: bool = False):
    """List available tools"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        tools = ToolRegistry.load()

        print(f"\n📋 Available Tools ({len(tools)} total):")
        print("=" * 50)

        for name, meta in tools.items():
            print(f"\n🔧 {name}")
            print(f"   Description: {meta.get('description', 'No description')}")

            if meta.get("inputs"):
                print(f"   Inputs:")
                for input_name, input_type in meta["inputs"].items():
                    print(f"     - {input_name}: {input_type}")

            if meta.get("produces"):
                print(f"   Produces: {', '.join(meta['produces'])}")

        return True

    except Exception as e:
        logger.error(f"Failed to list tools: {e}")
        return False


def list_events(verbose: bool = False):
    """List available events"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        # Get external events
        external_events = EventRegistry.get_external_events()

        print(f"\n📅 Available External Events ({len(external_events)} total):")
        print("=" * 50)

        for name, event_def in external_events.items():
            print(f"\n⚡ {name}")
            print(f"   Kind: {event_def.kind}")
            print(f"   Description: {event_def.description or 'No description'}")
            if event_def.schedule_pattern:
                print(f"   Schedule: {event_def.schedule_pattern}")
            if event_def.required_data:
                print(f"   Required Data: {', '.join(event_def.required_data)}")

        return True

    except Exception as e:
        logger.error(f"Failed to list events: {e}")
        return False


def execute_plan_command(plan_file: str, user_id: str, verbose: bool = False) -> bool:
    """Execute a plan command"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        from .planner import execute_plan

        logger.info(f"Executing plan from: {plan_file}")
        logger.info(f"User ID: {user_id}")

        # Execute the plan
        event = execute_plan(plan_file, user_id)

        logger.info("✅ Plan execution event created successfully")
        logger.info(f"Event type: {event['type']}")
        logger.info(f"Plan name: {event['metadata']['plan']['plan_name']}")

        # In a real implementation, this event would be sent to VextirOS event bus
        logger.info("📤 Event ready to be sent to VextirOS for processing")

        return True

    except Exception as e:
        logger.error(f"Failed to execute plan: {e}")
        return False


def setup_plan_command(plan_file: str, user_id: str, verbose: bool = False) -> bool:
    """Set up a plan command"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        from .planner import setup_plan

        logger.info(f"Setting up plan from: {plan_file}")
        logger.info(f"User ID: {user_id}")

        # Set up the plan
        event = setup_plan(plan_file, user_id)

        logger.info("✅ Plan setup event created successfully")
        logger.info(f"Event type: {event['type']}")
        logger.info(f"Plan name: {event['metadata']['plan']['plan_name']}")

        # In a real implementation, this event would be sent to VextirOS event bus
        logger.info("📤 Event ready to be sent to VextirOS for processing")

        return True

    except Exception as e:
        logger.error(f"Failed to set up plan: {e}")
        return False


def register_plan_application(
    plan_file: str, user_id: str, verbose: bool = False
) -> bool:
    """Register a plan as a first-class application"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        from .planner import register_application

        logger.info(f"Registering plan as application: {plan_file}")
        logger.info(f"User ID: {user_id}")

        # Register the plan application
        result = register_application(plan_file, user_id)

        logger.info("✅ Plan application registered successfully")
        logger.info(f"Application ID: {result['id']}")

        return True

    except Exception as e:
        logger.error(f"Failed to register plan application: {e}")
        return False


def unregister_plan_application(
    plan_id: str, user_id: str, verbose: bool = False
) -> bool:
    """Unregister a plan application"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        from .planner import unregister_application

        logger.info(f"Unregistering plan application: {plan_id}")
        logger.info(f"User ID: {user_id}")

        # Unregister the plan application
        result = unregister_application(plan_id, user_id)

        logger.info("✅ Plan application unregistered successfully")

        return True

    except Exception as e:
        logger.error(f"Failed to unregister plan application: {e}")
        return False


def list_plan_applications(verbose: bool = False):
    """List all registered plan applications"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        from .planner import list_applications

        logger.info("Listing all registered plan applications...")

        # Get the list of registered applications
        applications = list_applications()

        if not applications or len(applications) == 0:
            logger.info("No plan applications registered")
            return True

        # Display each application
        for app in applications:
            logger.info(f"Application ID: {app['id']}")
            logger.info(f"  Plan name: {app['plan_name']}")
            logger.info(f"  User ID: {app['user_id']}")
            logger.info(f"  Status: {app['status']}")
            logger.info(f"  Created at: {app['created_at']}")
            logger.info(f"  Updated at: {app['updated_at']}")
            logger.info("-" * 40)

        return True

    except Exception as e:
        logger.error(f"Failed to list plan applications: {e}")
        return False


def show_plan_application(plan_id: str, verbose: bool = False):
    """Show details of a specific plan application"""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        from .planner import get_application_details

        logger.info(f"Showing details for plan application: {plan_id}")

        # Get the application details
        app_details = get_application_details(plan_id)

        if not app_details:
            logger.error("Plan application not found")
            return False

        # Display the application details
        logger.info(f"Application ID: {app_details['id']}")
        logger.info(f"  Plan name: {app_details['plan_name']}")
        logger.info(f"  User ID: {app_details['user_id']}")
        logger.info(f"  Status: {app_details['status']}")
        logger.info(f"  Created at: {app_details['created_at']}")
        logger.info(f"  Updated at: {app_details['updated_at']}")
        logger.info(f"  Plan JSON: {json.dumps(app_details['plan'], indent=2)}")

        return True

    except Exception as e:
        logger.error(f"Failed to show plan application details: {e}")
        return False


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Lightning Planner CLI - Generate and visualize workflow plans",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate a plan
  lightning-planner generate "Create a daily email summary workflow"
  
  # Generate and save plan
  lightning-planner generate "Weekly report generation" -o weekly_plan.json
  
  # Validate a plan
  lightning-planner validate weekly_plan.json
  
  # Visualize a plan
  lightning-planner visualize weekly_plan.json -o weekly_plan.png
  
  # Generate Mermaid diagram
  lightning-planner mermaid weekly_plan.json -o weekly_plan.md
  
  # List available tools and events
  lightning-planner list-tools
  lightning-planner list-events
        """,
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Generate command
    generate_parser = subparsers.add_parser(
        "generate", help="Generate a plan from instruction"
    )
    generate_parser.add_argument(
        "instruction", help="Natural language instruction for the plan"
    )
    generate_parser.add_argument(
        "-o", "--output", help="Output file for the generated plan"
    )

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a plan file")
    validate_parser.add_argument("plan_file", help="Path to the plan JSON file")

    # Visualize command
    visualize_parser = subparsers.add_parser(
        "visualize", help="Generate visual representation of a plan"
    )
    visualize_parser.add_argument("plan_file", help="Path to the plan JSON file")
    visualize_parser.add_argument(
        "-o", "--output", help="Output file for the visualization"
    )
    visualize_parser.add_argument(
        "-f",
        "--format",
        default="png",
        choices=["png", "svg", "pdf"],
        help="Output format (default: png)",
    )

    # Mermaid command
    mermaid_parser = subparsers.add_parser(
        "mermaid", help="Generate Mermaid diagram of a plan"
    )
    mermaid_parser.add_argument("plan_file", help="Path to the plan JSON file")
    mermaid_parser.add_argument(
        "-o", "--output", help="Output file for the Mermaid diagram"
    )

    # Execute command
    execute_parser = subparsers.add_parser("execute", help="Execute a plan")
    execute_parser.add_argument("plan_file", help="Path to the plan JSON file")
    execute_parser.add_argument(
        "-u", "--user-id", default="default", help="User ID for plan execution"
    )

    # Setup command
    setup_parser = subparsers.add_parser(
        "setup", help="Set up a plan without executing it"
    )
    setup_parser.add_argument("plan_file", help="Path to the plan JSON file")
    setup_parser.add_argument(
        "-u", "--user-id", default="default", help="User ID for plan setup"
    )

    # List commands
    subparsers.add_parser("list-tools", help="List available tools")
    subparsers.add_parser("list-events", help="List available external events")

    # Plan application management commands
    register_parser = subparsers.add_parser(
        "register-app", help="Register a plan as a first-class application"
    )
    register_parser.add_argument("plan_file", help="Path to the plan JSON file")
    register_parser.add_argument(
        "-u", "--user-id", default="default", help="User ID for plan registration"
    )

    unregister_parser = subparsers.add_parser(
        "unregister-app", help="Unregister a plan application"
    )
    unregister_parser.add_argument("plan_id", help="ID of the plan to unregister")
    unregister_parser.add_argument(
        "-u", "--user-id", default="default", help="User ID for plan unregistration"
    )

    subparsers.add_parser("list-apps", help="List all registered plan applications")

    show_app_parser = subparsers.add_parser(
        "show-app", help="Show details of a specific plan application"
    )
    show_app_parser.add_argument("plan_id", help="ID of the plan to show")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "generate":
            plan = generate_plan(args.instruction, args.output, args.verbose)
            if not args.output:
                print(json.dumps(plan, indent=2))
            return 0

        elif args.command == "validate":
            success = validate_plan_file(args.plan_file, args.verbose)
            return 0 if success else 1

        elif args.command == "visualize":
            success = visualize_plan(
                args.plan_file, args.output, args.format, args.verbose
            )
            return 0 if success else 1

        elif args.command == "mermaid":
            success = generate_mermaid_diagram(
                args.plan_file, args.output, args.verbose
            )
            return 0 if success else 1

        elif args.command == "list-tools":
            success = list_tools(args.verbose)
            return 0 if success else 1

        elif args.command == "execute":
            success = execute_plan_command(args.plan_file, args.user_id, args.verbose)
            return 0 if success else 1

        elif args.command == "setup":
            success = setup_plan_command(args.plan_file, args.user_id, args.verbose)
            return 0 if success else 1

        elif args.command == "list-events":
            success = list_events(args.verbose)
            return 0 if success else 1

        elif args.command == "register-app":
            success = register_plan_application(
                args.plan_file, args.user_id, args.verbose
            )
            return 0 if success else 1

        elif args.command == "unregister-app":
            success = unregister_plan_application(
                args.plan_id, args.user_id, args.verbose
            )
            return 0 if success else 1

        elif args.command == "list-apps":
            success = list_plan_applications(args.verbose)
            return 0 if success else 1

        elif args.command == "show-app":
            success = show_plan_application(args.plan_id, args.verbose)
            return 0 if success else 1

        else:
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
