"""Field-level audit trail (spec §3.12, §7.3).

An after_flush listener inserts audit_log rows on the same connection, so a change and
its audit record commit (or roll back) together. Services can label an entry by setting
``obj._audit_action`` / ``obj._audit_note`` (and ``asset._audit_employee_id`` to show the
entry on that employee's timeline) before flushing.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .extensions import db
from .models import Acknowledgement, Asset, AuditLog, Employee, utcnow

EXCLUDED_FIELDS = {
    "password_hash",
    "token_hash",
    "created_at",
    "updated_at",
    "created_by_id",
    "updated_by_id",
}


def _actor_id() -> int | None:
    if not has_request_context() or request.blueprint == "ack":
        return None  # employee responses via the public link are never an IT user's action
    if current_user and current_user.is_authenticated:
        return current_user.id
    return None


def _ip() -> str | None:
    return request.remote_addr if has_request_context() else None


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _links(obj) -> tuple[int | None, int | None]:
    if isinstance(obj, Asset):
        return obj.id, getattr(obj, "_audit_employee_id", None)
    if isinstance(obj, Employee):
        return None, obj.id
    if isinstance(obj, Acknowledgement):
        return obj.assignment.asset_id, obj.assignment.employee_id
    return getattr(obj, "asset_id", None), getattr(obj, "employee_id", None)


def _row(obj, action: str, changes: dict | None) -> dict:
    asset_id, employee_id = _links(obj)
    return {
        "occurred_at": utcnow(),
        "user_id": _actor_id(),
        "ip_address": _ip(),
        "entity_type": type(obj).__tablename__,
        "entity_id": obj.id,
        "entity_label": obj.audit_label(),
        "action": getattr(obj, "_audit_action", None) or action,
        "changes": changes,
        "note": getattr(obj, "_audit_note", None),
        "asset_id": asset_id,
        "employee_id": employee_id,
    }


def _column_changes(obj, *, created: bool) -> dict:
    state = inspect(obj)
    changes = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in EXCLUDED_FIELDS:
            continue
        hist = state.attrs[key].history
        if created:
            value = getattr(obj, key)
            if value is not None and key != "id":
                changes[key] = [None, _jsonable(value)]
        elif hist.has_changes():
            old = hist.deleted[0] if hist.deleted else None
            new = hist.added[0] if hist.added else None
            if old != new:
                changes[key] = [_jsonable(old), _jsonable(new)]
    return changes


def _clear_hints(obj) -> None:
    for attr in ("_audit_action", "_audit_note", "_audit_employee_id"):
        obj.__dict__.pop(attr, None)


@event.listens_for(Session, "before_flush")
def _stamp_users(session, flush_context, instances):
    actor = _actor_id()
    for obj in session.new:
        if getattr(obj, "__audited__", False) and obj.created_by_id is None:
            obj.created_by_id = actor
    for obj in session.dirty:
        if getattr(obj, "__audited__", False) and session.is_modified(obj):
            obj.updated_by_id = actor


@event.listens_for(Session, "after_flush")
def _write_audit(session, flush_context):
    if session.info.get("skip_audit"):
        return
    rows = []
    for obj in session.new:
        if getattr(obj, "__audited__", False):
            rows.append(_row(obj, "create", _column_changes(obj, created=True)))
            _clear_hints(obj)
    for obj in session.dirty:
        if getattr(obj, "__audited__", False):
            changes = _column_changes(obj, created=False)
            if changes:
                action = "status_change" if "status" in changes else "update"
                rows.append(_row(obj, action, changes))
            _clear_hints(obj)
    for obj in session.deleted:
        if getattr(obj, "__audited__", False):
            rows.append(_row(obj, "delete", None))
    if rows:
        session.connection().execute(AuditLog.__table__.insert(), rows)


def timeline_filter():
    """Detail-page timelines skip creates of linked records; the asset entry already says it."""
    return ~((AuditLog.action == "create") & AuditLog.entity_type.not_in(["asset", "employee"]))


def log_event(action: str, *, entity_type: str, entity_id: int | None = None,
              label: str | None = None, note: str | None = None, user_id: int | None = None) -> None:
    """Record a non-data event (login, logout, failed login, export, ...)."""
    db.session.add(AuditLog(
        user_id=user_id if user_id is not None else _actor_id(),
        ip_address=_ip(),
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=label,
        action=action,
        note=note,
    ))
