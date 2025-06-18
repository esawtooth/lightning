"""
Scheduler drivers for VextirOS - Handle time-based events and cron scheduling
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from croniter import croniter

from .drivers import (
    Driver,
    DriverManifest,
    DriverType,
    ResourceSpec,
    ToolDriver,
    driver,
)
from .events import Event


@driver(
    "cron_scheduler",
    DriverType.TOOL,
    capabilities=["time.cron", "schedule.manage", "plan.schedule"],
    name="Cron Scheduler Driver",
    description="Handles cron-based scheduling for time events",
)
class CronSchedulerDriver(ToolDriver):
    """Driver that handles cron scheduling for time-based events"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.scheduled_jobs: Dict[str, Dict[str, Any]] = {}
        self.scheduler_thread: Optional[threading.Thread] = None
        self.running = False
        self.check_interval = (
            config.get("check_interval", 60) if config else 60
        )  # Check every minute

    def get_capabilities(self) -> List[str]:
        return ["time.cron", "schedule.manage", "plan.schedule"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=256, timeout_seconds=5)

    async def initialize(self):
        """Initialize the cron scheduler"""
        await super().initialize()
        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True
        )
        self.scheduler_thread.start()
        logging.info("Cron scheduler initialized and started")

    async def shutdown(self):
        """Shutdown the cron scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        await super().shutdown()
        logging.info("Cron scheduler shut down")

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle scheduling-related events"""
        output_events = []

        if event.type == "plan.schedule":
            # Schedule a plan's cron events
            plan = event.metadata.get("plan", {})
            await self._schedule_plan_events(plan, event.user_id)

            result_event = Event(
                timestamp=datetime.utcnow(),
                source="CronSchedulerDriver",
                type="plan.scheduled",
                user_id=event.user_id,
                metadata={
                    "plan_name": plan.get("plan_name", "unknown"),
                    "scheduled_events": len(
                        [
                            e
                            for e in plan.get("events", [])
                            if e.get("kind") == "time.cron"
                        ]
                    ),
                },
            )
            output_events.append(result_event)

        elif event.type == "schedule.add":
            # Add a single cron job
            job_id = event.metadata.get("job_id")
            cron_expression = event.metadata.get("cron_expression")
            event_name = event.metadata.get("event_name")

            if job_id and cron_expression and event_name:
                self._add_cron_job(job_id, cron_expression, event_name, event.user_id)

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="CronSchedulerDriver",
                    type="schedule.added",
                    user_id=event.user_id,
                    metadata={
                        "job_id": job_id,
                        "event_name": event_name,
                        "cron_expression": cron_expression,
                    },
                )
                output_events.append(result_event)

        elif event.type == "schedule.remove":
            # Remove a cron job
            job_id = event.metadata.get("job_id")
            if job_id:
                removed = self._remove_cron_job(job_id)

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="CronSchedulerDriver",
                    type="schedule.removed" if removed else "schedule.not_found",
                    user_id=event.user_id,
                    metadata={"job_id": job_id, "removed": removed},
                )
                output_events.append(result_event)

        return output_events

    async def _schedule_plan_events(self, plan: Dict[str, Any], user_id: str):
        """Schedule all cron events from a plan"""
        plan_name = plan.get("plan_name", "unknown")

        for event_def in plan.get("events", []):
            if event_def.get("kind") == "time.cron":
                event_name = event_def["name"]
                cron_expression = event_def.get(
                    "schedule", "0 20 * * *"
                )  # Default to 8 PM daily

                # Create unique job ID
                job_id = f"{plan_name}_{event_name}_{user_id}"

                self._add_cron_job(
                    job_id,
                    cron_expression,
                    event_name,
                    user_id,
                    {"plan_name": plan_name, "event_definition": event_def},
                )

                logging.info(
                    f"Scheduled cron job {job_id}: {cron_expression} -> {event_name}"
                )

    def _add_cron_job(
        self,
        job_id: str,
        cron_expression: str,
        event_name: str,
        user_id: str,
        metadata: Optional[Dict] = None,
    ):
        """Add a cron job to the scheduler"""
        try:
            # Validate cron expression
            cron = croniter(cron_expression)
            next_run = cron.get_next(datetime)

            self.scheduled_jobs[job_id] = {
                "cron_expression": cron_expression,
                "event_name": event_name,
                "user_id": user_id,
                "next_run": next_run,
                "metadata": metadata or {},
                "created_at": datetime.utcnow(),
                "run_count": 0,
            }

            logging.info(f"Added cron job {job_id}, next run: {next_run}")

        except Exception as e:
            logging.error(f"Failed to add cron job {job_id}: {e}")

    def _remove_cron_job(self, job_id: str) -> bool:
        """Remove a cron job from the scheduler"""
        if job_id in self.scheduled_jobs:
            del self.scheduled_jobs[job_id]
            logging.info(f"Removed cron job {job_id}")
            return True
        return False

    def _scheduler_loop(self):
        """Main scheduler loop that runs in a separate thread"""
        logging.info("Cron scheduler loop started")

        while self.running:
            try:
                current_time = datetime.utcnow()
                jobs_to_run = []

                # Check which jobs need to run
                for job_id, job_info in self.scheduled_jobs.items():
                    if current_time >= job_info["next_run"]:
                        jobs_to_run.append((job_id, job_info))

                # Execute jobs that are due
                for job_id, job_info in jobs_to_run:
                    try:
                        self._execute_job(job_id, job_info)

                        # Update next run time
                        cron = croniter(job_info["cron_expression"], current_time)
                        job_info["next_run"] = cron.get_next(datetime)
                        job_info["run_count"] += 1
                        job_info["last_run"] = current_time

                        logging.info(
                            f"Executed job {job_id}, next run: {job_info['next_run']}"
                        )

                    except Exception as e:
                        logging.error(f"Error executing job {job_id}: {e}")

                # Sleep until next check
                time.sleep(self.check_interval)

            except Exception as e:
                logging.error(f"Error in scheduler loop: {e}")
                time.sleep(self.check_interval)

        logging.info("Cron scheduler loop stopped")

    def _execute_job(self, job_id: str, job_info: Dict[str, Any]):
        """Execute a scheduled job by emitting the corresponding event"""
        try:
            # Create the scheduled event
            event = Event(
                timestamp=datetime.utcnow(),
                source="CronSchedulerDriver",
                type=job_info["event_name"],
                user_id=job_info["user_id"],
                metadata={
                    "job_id": job_id,
                    "cron_expression": job_info["cron_expression"],
                    "run_count": job_info["run_count"],
                    "scheduled_time": job_info["next_run"].isoformat(),
                    **job_info.get("metadata", {}),
                },
            )

            # Emit the event to the event bus
            # Note: This needs to be done asynchronously, but we're in a sync thread
            # In a production system, you'd use a queue or async mechanism
            asyncio.run_coroutine_threadsafe(
                self.event_bus.emit(event), asyncio.get_event_loop()
            )

            logging.info(
                f"Emitted scheduled event {job_info['event_name']} for job {job_id}"
            )

        except Exception as e:
            logging.error(f"Failed to execute job {job_id}: {e}")

    def get_job_status(self) -> Dict[str, Any]:
        """Get status of all scheduled jobs"""
        return {
            "total_jobs": len(self.scheduled_jobs),
            "running": self.running,
            "jobs": {
                job_id: {
                    "event_name": job_info["event_name"],
                    "user_id": job_info["user_id"],
                    "cron_expression": job_info["cron_expression"],
                    "next_run": job_info["next_run"].isoformat(),
                    "run_count": job_info["run_count"],
                    "created_at": job_info["created_at"].isoformat(),
                    "last_run": (
                        job_info.get("last_run", {}).isoformat()
                        if job_info.get("last_run")
                        else None
                    ),
                }
                for job_id, job_info in self.scheduled_jobs.items()
            },
        }


@driver(
    "interval_scheduler",
    DriverType.TOOL,
    capabilities=["time.interval", "schedule.interval"],
    name="Interval Scheduler Driver",
    description="Handles interval-based scheduling for time events",
)
class IntervalSchedulerDriver(ToolDriver):
    """Driver that handles interval-based scheduling (e.g., every 5 minutes)"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.scheduled_intervals: Dict[str, Dict[str, Any]] = {}
        self.scheduler_thread: Optional[threading.Thread] = None
        self.running = False
        self.check_interval = (
            config.get("check_interval", 30) if config else 30
        )  # Check every 30 seconds

    def get_capabilities(self) -> List[str]:
        return ["time.interval", "schedule.interval"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=128, timeout_seconds=5)

    async def initialize(self):
        """Initialize the interval scheduler"""
        await super().initialize()
        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True
        )
        self.scheduler_thread.start()
        logging.info("Interval scheduler initialized and started")

    async def shutdown(self):
        """Shutdown the interval scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        await super().shutdown()
        logging.info("Interval scheduler shut down")

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle interval scheduling events"""
        output_events = []

        if event.type == "plan.schedule":
            # Schedule a plan's interval events
            plan = event.metadata.get("plan", {})
            await self._schedule_plan_intervals(plan, event.user_id)

            result_event = Event(
                timestamp=datetime.utcnow(),
                source="IntervalSchedulerDriver",
                type="plan.intervals.scheduled",
                user_id=event.user_id,
                metadata={
                    "plan_name": plan.get("plan_name", "unknown"),
                    "scheduled_intervals": len(
                        [
                            e
                            for e in plan.get("events", [])
                            if e.get("kind") == "time.interval"
                        ]
                    ),
                },
            )
            output_events.append(result_event)

        return output_events

    async def _schedule_plan_intervals(self, plan: Dict[str, Any], user_id: str):
        """Schedule all interval events from a plan"""
        plan_name = plan.get("plan_name", "unknown")

        for event_def in plan.get("events", []):
            if event_def.get("kind") == "time.interval":
                event_name = event_def["name"]
                interval_str = event_def.get("schedule", "PT5M")  # Default to 5 minutes

                # Parse ISO 8601 duration (e.g., PT5M = 5 minutes)
                interval_seconds = self._parse_iso_duration(interval_str)

                if interval_seconds:
                    job_id = f"{plan_name}_{event_name}_{user_id}"

                    self._add_interval_job(
                        job_id,
                        interval_seconds,
                        event_name,
                        user_id,
                        {"plan_name": plan_name, "event_definition": event_def},
                    )

                    logging.info(
                        f"Scheduled interval job {job_id}: every {interval_seconds}s -> {event_name}"
                    )

    def _parse_iso_duration(self, duration_str: str) -> Optional[int]:
        """Parse ISO 8601 duration string to seconds"""
        try:
            # Simple parser for common patterns like PT5M, PT1H, PT30S
            if not duration_str.startswith("PT"):
                return None

            duration_str = duration_str[2:]  # Remove "PT"
            seconds = 0

            # Parse hours
            if "H" in duration_str:
                hours_part, duration_str = duration_str.split("H", 1)
                seconds += int(hours_part) * 3600

            # Parse minutes
            if "M" in duration_str:
                minutes_part, duration_str = duration_str.split("M", 1)
                seconds += int(minutes_part) * 60

            # Parse seconds
            if "S" in duration_str:
                seconds_part = duration_str.replace("S", "")
                seconds += int(seconds_part)

            return seconds if seconds > 0 else None

        except Exception as e:
            logging.error(f"Failed to parse duration {duration_str}: {e}")
            return None

    def _add_interval_job(
        self,
        job_id: str,
        interval_seconds: int,
        event_name: str,
        user_id: str,
        metadata: Optional[Dict] = None,
    ):
        """Add an interval job to the scheduler"""
        next_run = datetime.utcnow() + timedelta(seconds=interval_seconds)

        self.scheduled_intervals[job_id] = {
            "interval_seconds": interval_seconds,
            "event_name": event_name,
            "user_id": user_id,
            "next_run": next_run,
            "metadata": metadata or {},
            "created_at": datetime.utcnow(),
            "run_count": 0,
        }

        logging.info(f"Added interval job {job_id}, next run: {next_run}")

    def _scheduler_loop(self):
        """Main scheduler loop for intervals"""
        logging.info("Interval scheduler loop started")

        while self.running:
            try:
                current_time = datetime.utcnow()
                jobs_to_run = []

                # Check which jobs need to run
                for job_id, job_info in self.scheduled_intervals.items():
                    if current_time >= job_info["next_run"]:
                        jobs_to_run.append((job_id, job_info))

                # Execute jobs that are due
                for job_id, job_info in jobs_to_run:
                    try:
                        self._execute_job(job_id, job_info)

                        # Update next run time
                        job_info["next_run"] = current_time + timedelta(
                            seconds=job_info["interval_seconds"]
                        )
                        job_info["run_count"] += 1
                        job_info["last_run"] = current_time

                        logging.info(
                            f"Executed interval job {job_id}, next run: {job_info['next_run']}"
                        )

                    except Exception as e:
                        logging.error(f"Error executing interval job {job_id}: {e}")

                # Sleep until next check
                time.sleep(self.check_interval)

            except Exception as e:
                logging.error(f"Error in interval scheduler loop: {e}")
                time.sleep(self.check_interval)

        logging.info("Interval scheduler loop stopped")

    def _execute_job(self, job_id: str, job_info: Dict[str, Any]):
        """Execute a scheduled interval job"""
        try:
            # Create the scheduled event
            event = Event(
                timestamp=datetime.utcnow(),
                source="IntervalSchedulerDriver",
                type=job_info["event_name"],
                user_id=job_info["user_id"],
                metadata={
                    "job_id": job_id,
                    "interval_seconds": job_info["interval_seconds"],
                    "run_count": job_info["run_count"],
                    "scheduled_time": job_info["next_run"].isoformat(),
                    **job_info.get("metadata", {}),
                },
            )

            # Emit the event to the event bus
            asyncio.run_coroutine_threadsafe(
                self.event_bus.emit(event), asyncio.get_event_loop()
            )

            logging.info(
                f"Emitted scheduled interval event {job_info['event_name']} for job {job_id}"
            )

        except Exception as e:
            logging.error(f"Failed to execute interval job {job_id}: {e}")
