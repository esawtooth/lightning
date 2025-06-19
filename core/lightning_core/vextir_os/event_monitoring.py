"""
Event monitoring and metrics for Lightning Core.

Provides monitoring capabilities for event processing, including
orphaned events, dead letter queues, and processing metrics.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from lightning_core.abstractions import get_provider_factory
from lightning_core.vextir_os.universal_processor import get_universal_processor

logger = logging.getLogger(__name__)


class EventMonitor:
    """Monitor event processing health and metrics."""

    def __init__(self):
        self.factory = get_provider_factory()
        self.event_bus = self.factory.create_event_bus()
        self.processor = get_universal_processor()

    async def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status of event processing."""
        metrics = await self.processor.get_metrics()
        orphaned_events = await self.event_bus.get_orphaned_events(max_items=100)
        dead_letter_events = await self.event_bus.get_dead_letter_events(max_items=100)

        # Calculate health score (0-100)
        health_score = 100
        
        # Deduct points for high error rate
        error_rate = metrics.get("error_rate", 0)
        if error_rate > 0.1:  # More than 10% errors
            health_score -= min(30, int(error_rate * 100))
        
        # Deduct points for high orphan rate
        orphan_rate = metrics.get("orphan_rate", 0)
        if orphan_rate > 0.2:  # More than 20% orphaned
            health_score -= min(40, int(orphan_rate * 100))
        
        # Deduct points for dead letter queue size
        if len(dead_letter_events) > 50:
            health_score -= 20
        elif len(dead_letter_events) > 10:
            health_score -= 10

        # Determine status
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "degraded"
        else:
            status = "unhealthy"

        return {
            "status": status,
            "health_score": health_score,
            "metrics": metrics,
            "orphaned_event_count": len(orphaned_events),
            "dead_letter_count": len(dead_letter_events),
            "timestamp": datetime.utcnow().isoformat()
        }

    async def get_orphaned_event_summary(self) -> Dict[str, Any]:
        """Get summary of orphaned events."""
        orphaned_events = await self.event_bus.get_orphaned_events()
        
        # Group by event type
        by_type = {}
        for event in orphaned_events:
            event_type = event.event_type
            if event_type not in by_type:
                by_type[event_type] = {
                    "count": 0,
                    "first_seen": event.timestamp,
                    "last_seen": event.timestamp,
                    "sample_ids": []
                }
            
            by_type[event_type]["count"] += 1
            by_type[event_type]["last_seen"] = max(
                by_type[event_type]["last_seen"], 
                event.timestamp
            )
            if len(by_type[event_type]["sample_ids"]) < 5:
                by_type[event_type]["sample_ids"].append(event.id)

        return {
            "total_count": len(orphaned_events),
            "by_event_type": by_type,
            "recommendation": self._get_orphan_recommendation(by_type)
        }

    async def get_processing_metrics(self) -> Dict[str, Any]:
        """Get detailed processing metrics."""
        metrics = await self.processor.get_metrics()
        
        # Add additional calculated metrics
        total_processed = metrics.get("total_events", 0)
        total_errors = metrics.get("total_errors", 0)
        total_orphaned = metrics.get("total_orphaned", 0)
        
        success_count = total_processed - total_errors - total_orphaned
        success_rate = success_count / max(total_processed, 1)
        
        return {
            **metrics,
            "success_count": success_count,
            "success_rate": success_rate,
            "events_per_minute": self._calculate_events_per_minute(total_processed),
            "top_event_types": self._get_top_event_types(metrics.get("event_types", {})),
            "top_error_types": self._get_top_error_types(metrics.get("error_types", {})),
            "top_orphaned_types": self._get_top_orphaned_types(metrics.get("orphaned_types", {}))
        }

    async def cleanup_orphaned_events(
        self, 
        event_types: Optional[List[str]] = None,
        older_than_hours: int = 24
    ) -> Dict[str, Any]:
        """Clean up orphaned events older than specified hours."""
        before = datetime.utcnow() - timedelta(hours=older_than_hours)
        
        # Get count before cleanup
        orphaned_before = await self.event_bus.get_orphaned_events()
        count_before = len(orphaned_before)
        
        # Perform cleanup
        drained_count = await self.event_bus.drain_orphaned_events(
            event_types=event_types,
            before=before
        )
        
        # Get count after cleanup
        orphaned_after = await self.event_bus.get_orphaned_events()
        count_after = len(orphaned_after)
        
        return {
            "drained_count": drained_count,
            "orphaned_before": count_before,
            "orphaned_after": count_after,
            "event_types_filter": event_types,
            "older_than_hours": older_than_hours,
            "cleanup_timestamp": datetime.utcnow().isoformat()
        }

    def _get_orphan_recommendation(self, by_type: Dict[str, Any]) -> str:
        """Get recommendation for handling orphaned events."""
        if not by_type:
            return "No orphaned events detected. System is healthy."
        
        recommendations = []
        
        for event_type, info in by_type.items():
            if info["count"] > 100:
                recommendations.append(
                    f"High volume of orphaned '{event_type}' events ({info['count']}). "
                    f"Consider adding a driver or subscriber for this event type."
                )
            elif info["count"] > 10:
                recommendations.append(
                    f"Moderate orphaned '{event_type}' events ({info['count']}). "
                    f"Review if this event type is still needed."
                )
        
        if not recommendations:
            return "Low volume of orphaned events. Consider periodic cleanup."
        
        return " ".join(recommendations)

    def _calculate_events_per_minute(self, total_events: int) -> float:
        """Calculate approximate events per minute (simplified)."""
        # This is a simplified calculation
        # In production, you'd track actual time windows
        return total_events / max(1, 60)  # Assume running for 60 minutes

    def _get_top_event_types(self, event_types: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
        """Get top event types by count."""
        sorted_types = sorted(event_types.items(), key=lambda x: x[1], reverse=True)
        return [
            {"event_type": event_type, "count": count}
            for event_type, count in sorted_types[:limit]
        ]

    def _get_top_error_types(self, error_types: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
        """Get top error types by count."""
        sorted_types = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
        return [
            {"error_type": error_type, "count": count}
            for error_type, count in sorted_types[:limit]
        ]

    def _get_top_orphaned_types(self, orphaned_types: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
        """Get top orphaned event types by count."""
        sorted_types = sorted(orphaned_types.items(), key=lambda x: x[1], reverse=True)
        return [
            {"event_type": event_type, "count": count}
            for event_type, count in sorted_types[:limit]
        ]


# Global monitor instance
_global_monitor: Optional[EventMonitor] = None


def get_event_monitor() -> EventMonitor:
    """Get global event monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = EventMonitor()
    return _global_monitor


async def monitor_events_continuously(interval_seconds: int = 60):
    """Run continuous monitoring and log warnings."""
    monitor = get_event_monitor()
    
    while True:
        try:
            # Get health status
            health = await monitor.get_health_status()
            
            if health["status"] == "unhealthy":
                logger.error(f"Event processing unhealthy: score={health['health_score']}")
            elif health["status"] == "degraded":
                logger.warning(f"Event processing degraded: score={health['health_score']}")
            
            # Check orphaned events
            orphan_summary = await monitor.get_orphaned_event_summary()
            if orphan_summary["total_count"] > 100:
                logger.warning(
                    f"High orphaned event count: {orphan_summary['total_count']}. "
                    f"{orphan_summary['recommendation']}"
                )
            
            # Log metrics summary
            metrics = await monitor.get_processing_metrics()
            logger.info(
                f"Event processing metrics: "
                f"total={metrics['total_events']}, "
                f"success_rate={metrics['success_rate']:.2%}, "
                f"orphan_rate={metrics['orphan_rate']:.2%}"
            )
            
            await asyncio.sleep(interval_seconds)
            
        except Exception as e:
            logger.error(f"Error in event monitoring: {e}")
            await asyncio.sleep(interval_seconds)