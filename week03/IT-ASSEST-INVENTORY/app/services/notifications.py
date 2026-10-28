"""Email notifications (spec §3.10).

No SMTP account is configured yet (open question 3), so messages are written to
email_log with status LOGGED instead of being sent.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta

from flask import current_app, url_for
from sqlalchemy import func, select

from ..extensions import db
from ..models import (
    Acknowledgement,
    AckStatus,
    Asset,
    AssetModel,
    AssetStatus,
    Assignment,
    EmailLog,
    utcnow,
)


def send_email(to: str, template_code: str, subject: str, body: str) -> EmailLog:
    entry = EmailLog(to_address=to, template_code=template_code, subject=subject, body=body)
    db.session.add(entry)
    return entry


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(ack: Acknowledgement) -> str:
    """Give the acknowledgement a fresh single-use link (FR-ASN-02); older links stop working."""
    token = secrets.token_urlsafe(32)
    ack.token_hash = hash_token(token)
    ack.sent_at = utcnow()
    ack.expires_at = ack.sent_at + timedelta(days=current_app.config["ACK_VALID_DAYS"])
    ack.status = AckStatus.PENDING
    return token


def ack_link(token: str) -> str:
    return url_for("ack.respond", token=token, _external=True)


def send_acknowledgement(assignment: Assignment, token: str, *, reminder: bool = False) -> None:
    asset = assignment.asset
    emp = assignment.employee
    prefix = "Reminder: " if reminder else ""
    send_email(
        emp.email,
        "ACK_REMINDER" if reminder else "ACK_REQUEST",
        f"{prefix}Please confirm receipt of {asset.asset_tag}",
        f"Hello {emp.full_name},\n\n{asset.model.display_name} ({asset.asset_tag}, serial "
        f"{asset.serial_number}) has been assigned to you.\nPlease confirm receipt: {ack_link(token)}\n",
    )


def run_daily_job(today: date | None = None) -> dict[str, int]:
    """The 07:00 job: acknowledgement expiry, warranty, overdue returns and low stock."""
    today = today or date.today()
    now = utcnow()
    it_team = current_app.config["IT_TEAM_EMAIL"]
    counts = {"ack_expired": 0, "warranty": 0, "overdue": 0, "low_stock": 0}

    pending = db.session.scalars(
        select(Acknowledgement).where(Acknowledgement.status == AckStatus.PENDING)
    ).all()
    reminder_after = timedelta(days=current_app.config["ACK_REMINDER_DAYS"])
    counts["ack_reminders"] = 0
    for ack in pending:
        if ack.expires_at >= now and not ack.reminder_sent_at and now - ack.sent_at >= reminder_after:
            # Only the hash is stored, so the reminder carries a new link with the same expiry.
            expires = ack.expires_at
            token = issue_token(ack)
            ack.expires_at = expires
            ack.reminder_sent_at = now
            send_acknowledgement(ack.assignment, token, reminder=True)
            counts["ack_reminders"] += 1
        elif ack.expires_at < now:
            ack.status = AckStatus.EXPIRED
            counts["ack_expired"] += 1
            send_email(it_team, "ACK_EXPIRED", f"Acknowledgement expired: {ack.assignment.asset.asset_tag}",
                       f"{ack.assignment.employee.full_name} did not confirm receipt within 7 days.")

    for days in current_app.config["WARRANTY_NOTICE_DAYS"]:
        due = db.session.scalars(
            select(Asset).where(Asset.warranty_end_date == today + timedelta(days=days),
                                Asset.status.in_(AssetStatus.ACTIVE))
        ).all()
        if due:
            counts["warranty"] += len(due)
            send_email(it_team, "WARRANTY_DIGEST", f"{len(due)} warranties expire in {days} days",
                       "\n".join(f"{a.asset_tag} {a.model.display_name}" for a in due))

    open_assignments = db.session.scalars(
        select(Assignment).where(Assignment.checked_in_at.is_(None))
    ).all()
    overdue = [a for a in open_assignments if a.is_overdue(today)]
    for a in overdue:
        recipients = [it_team, a.employee.email] + ([a.employee.manager.email] if a.employee.manager else [])
        for to in recipients:
            send_email(to, "OVERDUE_RETURN", f"Overdue return: {a.asset.asset_tag}",
                       f"{a.asset.model.display_name} held by {a.employee.full_name} is overdue for return.")
    counts["overdue"] = len(overdue)

    for model, in_stock in low_stock_models():
        counts["low_stock"] += 1
        send_email(it_team, "LOW_STOCK", f"Low stock: {model.display_name}",
                   f"{in_stock} in stock, threshold {model.low_stock_threshold}.")

    db.session.commit()
    return counts


def low_stock_models() -> list[tuple[AssetModel, int]]:
    in_stock = (
        select(Asset.model_id, func.count().label("n"))
        .where(Asset.status == AssetStatus.IN_STOCK)
        .group_by(Asset.model_id)
        .subquery()
    )
    rows = db.session.execute(
        select(AssetModel, func.coalesce(in_stock.c.n, 0))
        .outerjoin(in_stock, in_stock.c.model_id == AssetModel.id)
        .where(AssetModel.low_stock_threshold.is_not(None))
    ).all()
    return [(m, n) for m, n in rows if n < m.low_stock_threshold]

