"""
Vextir OS Security Manager - Policy enforcement and authorization
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from events import Event


class PolicyAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    RESTRICT = "restrict"
    LOG = "log"
    NOTIFY = "notify"


@dataclass
class Policy:
    """Security/operational policy definition"""
    id: str
    name: str
    description: str
    condition: str  # Python expression to evaluate
    action: PolicyAction
    config: Dict[str, Any] = field(default_factory=dict)
    applies_to: List[str] = field(default_factory=list)  # user_ids or ["*"] for all
    enabled: bool = True
    priority: int = 100  # Lower number = higher priority


@dataclass
class PolicyEvaluation:
    """Result of policy evaluation"""
    policy: Policy
    matched: bool
    action: PolicyAction
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PolicyEngine:
    """Engine for evaluating policies against events"""
    
    def __init__(self):
        self.policies: Dict[str, Policy] = {}
        
    def add_policy(self, policy: Policy):
        """Add a policy to the engine"""
        self.policies[policy.id] = policy
        logging.info(f"Added policy: {policy.name}")
        
    def remove_policy(self, policy_id: str):
        """Remove a policy from the engine"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            logging.info(f"Removed policy: {policy_id}")
            
    async def evaluate_policies(self, event: Event, context: Dict[str, Any]) -> List[PolicyEvaluation]:
        """Evaluate all applicable policies against an event"""
        evaluations = []
        
        # Get applicable policies
        applicable_policies = []
        for policy in self.policies.values():
            if not policy.enabled:
                continue
                
            # Check if policy applies to this user
            if policy.applies_to and "*" not in policy.applies_to:
                if event.user_id not in policy.applies_to:
                    continue
                    
            applicable_policies.append(policy)
            
        # Sort by priority
        applicable_policies.sort(key=lambda p: p.priority)
        
        # Evaluate each policy
        for policy in applicable_policies:
            try:
                evaluation = await self._evaluate_policy(policy, event, context)
                evaluations.append(evaluation)
                
                # If policy denies, stop evaluation
                if evaluation.action == PolicyAction.DENY:
                    break
                    
            except Exception as e:
                logging.error(f"Error evaluating policy {policy.id}: {e}")
                
        return evaluations
        
    async def _evaluate_policy(self, policy: Policy, event: Event, context: Dict[str, Any]) -> PolicyEvaluation:
        """Evaluate a single policy"""
        # Build evaluation context
        eval_context = {
            "event": event,
            "event_type": event.type,
            "user_id": event.user_id,
            "source": event.source,
            "metadata": event.metadata,
            "timestamp": event.timestamp,
            **context
        }
        
        try:
            # Evaluate condition
            matched = eval(policy.condition, {"__builtins__": {}}, eval_context)
            
            if matched:
                return PolicyEvaluation(
                    policy=policy,
                    matched=True,
                    action=policy.action,
                    message=f"Policy {policy.name} triggered",
                    metadata={"condition": policy.condition}
                )
            else:
                return PolicyEvaluation(
                    policy=policy,
                    matched=False,
                    action=PolicyAction.ALLOW
                )
                
        except Exception as e:
            logging.error(f"Error in policy condition {policy.id}: {e}")
            return PolicyEvaluation(
                policy=policy,
                matched=False,
                action=PolicyAction.ALLOW,
                message=f"Policy evaluation error: {e}"
            )


class SecurityManager:
    """Main security manager for Vextir OS"""
    
    def __init__(self):
        self.policy_engine = PolicyEngine()
        self.audit_log: List[Dict[str, Any]] = []
        self.max_audit_log = 10000
        
        # Load default policies
        self._load_default_policies()
        
    async def authorize(self, event: Event) -> bool:
        """Authorize an event based on security policies"""
        # Build context for policy evaluation
        context = await self._build_context(event)
        
        # Evaluate policies
        evaluations = await self.policy_engine.evaluate_policies(event, context)
        
        # Determine final authorization
        authorized = True
        actions_taken = []
        
        for evaluation in evaluations:
            if evaluation.matched:
                if evaluation.action == PolicyAction.DENY:
                    authorized = False
                    actions_taken.append("DENIED")
                    break
                elif evaluation.action == PolicyAction.RESTRICT:
                    # Apply restrictions (implementation specific)
                    actions_taken.append("RESTRICTED")
                elif evaluation.action == PolicyAction.LOG:
                    actions_taken.append("LOGGED")
                elif evaluation.action == PolicyAction.NOTIFY:
                    actions_taken.append("NOTIFIED")
                    
        # Log authorization decision
        await self._log_authorization(event, authorized, evaluations, actions_taken)
        
        return authorized
        
    async def _build_context(self, event: Event) -> Dict[str, Any]:
        """Build context for policy evaluation"""
        # This could include user info, resource usage, etc.
        return {
            "current_time": datetime.utcnow(),
            "daily_events": 0,  # TODO: Get from metrics
            "monthly_cost": 0.0,  # TODO: Get from cost tracking
        }
        
    async def _log_authorization(self, event: Event, authorized: bool, evaluations: List[PolicyEvaluation], actions: List[str]):
        """Log authorization decision for audit"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_id": event.id,
            "event_type": event.type,
            "user_id": event.user_id,
            "authorized": authorized,
            "policies_evaluated": len(evaluations),
            "policies_matched": len([e for e in evaluations if e.matched]),
            "actions_taken": actions
        }
        
        self.audit_log.append(log_entry)
        
        # Limit audit log size
        if len(self.audit_log) > self.max_audit_log:
            self.audit_log = self.audit_log[-self.max_audit_log//2:]
            
    def _load_default_policies(self):
        """Load default security policies"""
        # Cost control policy
        cost_policy = Policy(
            id="cost_limit",
            name="Daily Cost Limit",
            description="Prevent excessive daily costs",
            condition="monthly_cost > 100.0",
            action=PolicyAction.DENY,
            applies_to=["*"],
            priority=10
        )
        self.policy_engine.add_policy(cost_policy)
        
        # Rate limiting policy
        rate_policy = Policy(
            id="rate_limit",
            name="Event Rate Limit",
            description="Limit events per user per day",
            condition="daily_events > 1000",
            action=PolicyAction.RESTRICT,
            applies_to=["*"],
            priority=20
        )
        self.policy_engine.add_policy(rate_policy)
        
        # PII protection policy
        pii_policy = Policy(
            id="pii_protection",
            name="PII Protection",
            description="Block external APIs for personal data",
            condition="event_type.startswith('context.') and 'Personal' in str(metadata)",
            action=PolicyAction.LOG,
            applies_to=["*"],
            priority=30
        )
        self.policy_engine.add_policy(pii_policy)
        
    def add_policy(self, policy: Policy):
        """Add a custom policy"""
        self.policy_engine.add_policy(policy)
        
    def remove_policy(self, policy_id: str):
        """Remove a policy"""
        self.policy_engine.remove_policy(policy_id)
        
    def list_policies(self) -> List[Policy]:
        """List all policies"""
        return list(self.policy_engine.policies.values())
        
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit log entries"""
        return self.audit_log[-limit:]


# Global security manager
_global_security_manager: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """Get global security manager instance"""
    global _global_security_manager
    if _global_security_manager is None:
        _global_security_manager = SecurityManager()
    return _global_security_manager
