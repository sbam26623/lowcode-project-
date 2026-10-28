"""Public acknowledgement page reached from the emailed link (FR-ASN-03, -04). No login."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template, request
from sqlalchemy import select

from ..extensions import db
from ..models import Acknowledgement, AckStatus, utcnow
from ..services.notifications import hash_token, send_email

bp = Blueprint("ack", __name__, url_prefix="/ack")

ACCEPTABLE_USE = [
    "The equipment remains the property of the company and must be returned on request or when you leave.",
    "Keep the device physically secure, locked when unattended and protected by the company's security software.",
    "Report loss, theft or damage to the IT team within 24 hours.",
    "Do not install unlicensed software or remove the asset tag.",
]


def _lookup(token: str) -> Acknowledgement | None:
    return db.session.scalar(select(Acknowledgement).where(Acknowledgement.token_hash == hash_token(token)))


@bp.route("/<token>", methods=["GET", "POST"])
def respond(token: str):
    ack = _lookup(token)
    if ack is None:
        return render_template("ack/message.html", title="Link not valid",
                               message="This acknowledgement link is invalid or has been replaced by a newer one."), 404
    if ack.status != AckStatus.PENDING or ack.effective_status == AckStatus.EXPIRED:
        status = ack.effective_status
        return render_template("ack/message.html", title=f"Already {status.lower()}",
                               message=f"This acknowledgement is {status.lower()}. Contact the IT team if "
                                       "something is wrong."), 410
    assignment = ack.assignment
    employee = assignment.employee
    error = None
    if request.method == "POST":
        typed = request.form.get("typed_name", "").strip()
        choice = request.form.get("choice")
        if choice == "accept":
            if typed.casefold() != employee.full_name.casefold():
                error = f"Type your full name exactly as shown: {employee.full_name}"
            else:
                ack.status = AckStatus.ACCEPTED
        elif choice == "dispute":
            if not request.form.get("comment", "").strip():
                error = "Tell us what is wrong so IT can follow up."
            else:
                ack.status = AckStatus.DISPUTED
                ack.comment = request.form["comment"].strip()
                send_email(current_app.config["IT_TEAM_EMAIL"], "ACK_DISPUTED",
                           f"Acknowledgement disputed: {assignment.asset.asset_tag}",
                           f"{employee.full_name}: {ack.comment}")
        if not error and choice in ("accept", "dispute"):
            ack.typed_name = typed or None
            ack.responded_at = utcnow()
            ack.ip_address = request.remote_addr
            ack.user_agent = (request.user_agent.string or "")[:400]
            ack.token_hash = None  # single use
            ack._audit_action = f"ack_{ack.status.lower()}"
            ack._audit_note = f"{employee.full_name} {ack.status.lower()} {assignment.asset.asset_tag}"
            db.session.commit()
            return render_template("ack/message.html", title="Thank you",
                                   message="Your response has been recorded." if ack.status == AckStatus.DISPUTED
                                   else f"You have confirmed receipt of {assignment.asset.asset_tag}.")
    return render_template("ack/page.html", ack=ack, assignment=assignment, employee=employee,
                           terms=ACCEPTABLE_USE, error=error)
