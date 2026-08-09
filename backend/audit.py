"""Audit log helper.

Writes immutable, insert-only rows to ``audit_logs`` for security-relevant
actions (registrations, logins, admin changes, dataset deletions, resets).
"""
from typing import Optional

from models import AuditLog


def write_audit(
    db,
    action: str,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
        )
    )
    db.commit()
