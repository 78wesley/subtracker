"""
audit.py — write_audit_log helper.
"""

import json
from database import get_db
import timeutil


def write_audit_log(user_id: int, action: str, entity_type: str, entity_id: int,
                    description: str, old_values=None, new_values=None) -> None:
    get_db()["audit_log"].insert({
        "user_id":     user_id,
        "action":      action,
        "entity_type": entity_type,
        "entity_id":   entity_id,
        "old_values":  json.dumps(old_values) if old_values else None,
        "new_values":  json.dumps(new_values) if new_values else None,
        "description": description,
        "timestamp":   timeutil.now_iso(),
    })
