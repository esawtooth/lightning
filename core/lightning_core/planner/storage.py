import datetime
import json
import logging
import uuid
from typing import Any, Dict

try:
    from azure.cosmos import CosmosClient, PartitionKey

    COSMOS = True
except ImportError:
    COSMOS = False

logger = logging.getLogger(__name__)


class PlanStore:
    """Persist plan templates in Cosmos or in‑memory fallback."""

    def __init__(self, endpoint: str = "", key: str = "", db_name="lightning"):
        if COSMOS:
            self.client = CosmosClient(endpoint, key)
            self.db = self.client.create_database_if_not_exists(db_name)
            self.container = self.db.create_container_if_not_exists(
                id="plans", partition_key=PartitionKey(path="/pk")
            )
        else:
            self.mem: Dict[str, Dict[str, Any]] = {}

    def save(self, user_id: str, plan: Dict[str, Any]) -> str:
        plan_id = str(uuid.uuid4())
        plan_record = dict(
            id=plan_id,
            pk=user_id,
            created_at=str(datetime.datetime.utcnow()),
            plan=plan,
            status="template",
        )
        if COSMOS:
            self.container.upsert_item(plan_record)
        else:
            self.mem[plan_id] = plan_record
        return plan_id
