"""Asset lifecycle rules (spec §3.5 - §3.7). Routes call these; they never set status directly."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ..extensions import db
from ..models import (
    Acknowledgement,
    AckStatus,
    Asset,
    AssetStatus as S,
    Assignment,
    Disposal,
    Employee,
    Repair,
    User,
    utcnow,
)
from . import notifications

ALLOWED: dict[str, set[str]] = {
    S.IN_STOCK: {S.ASSIGNED, S.IN_REPAIR, S.RETIRED},
    S.ASSIGNED: {S.IN_STOCK, S.IN_REPAIR},
    S.IN_REPAIR: {S.IN_STOCK, S.ASSIGNED, S.RETIRED},
    S.RETIRED: {S.DISPOSED, S.IN_STOCK},
    S.DISPOSED: set(),
}


class LifecycleError(Exception):
    pass


def _transition(asset: Asset, new_status: str, action: str, note: str | None = None) -> None:
    if new_status not in ALLOWED[asset.status]:
        raise LifecycleError(
            f"{asset.asset_tag} cannot move from {asset.status} to {new_status}."
        )
    asset.status = new_status
    asset._audit_action = action
    asset._audit_note = note


def open_assignment(asset: Asset) -> Assignment | None:
    return db.session.scalar(
        select(Assignment).where(Assignment.asset_id == asset.id, Assignment.checked_in_at.is_(None))
    )


def open_repair(asset: Asset) -> Repair | None:
    return db.session.scalar(
        select(Repair).where(Repair.asset_id == asset.id, Repair.completed_at.is_(None))
    )


def check_out(asset: Asset, employee: Employee, user: User, *, expected_return: date | None = None,
              condition: str = "Good", notes: str | None = None) -> tuple[Assignment, str]:
    """FR-ASN-01/02. Returns the assignment and the raw acknowledgement token."""
    if asset.status != S.IN_STOCK:
        raise LifecycleError(f"Only In Stock assets can be checked out; {asset.asset_tag} is {asset.status}.")
    if employee.status != "ACTIVE":
        raise LifecycleError(f"{employee.full_name} is a leaver and cannot receive assets.")
    assignment = Assignment(
        asset=asset, employee=employee, checked_out_by_id=user.id,
        expected_return_date=expected_return, checkout_condition=condition, notes=notes,
    )
    db.session.add(assignment)
    ack = Acknowledgement(assignment=assignment)
    token = notifications.issue_token(ack)
    db.session.add(ack)
    _transition(asset, S.ASSIGNED, "check_out", f"Checked out to {employee.audit_label()}")
    asset._audit_employee_id = employee.id
    if employee.location_id:
        asset.location_id = employee.location_id
    notifications.send_acknowledgement(assignment, token)
    return assignment, token


def resend_acknowledgement(assignment: Assignment) -> str:
    """FR-ASN-05: managers can resend the link; it is valid for another 7 days."""
    if not assignment.is_open:
        raise LifecycleError("This assignment is closed.")
    ack = assignment.acknowledgement
    if ack.status == AckStatus.ACCEPTED:
        raise LifecycleError("The employee has already accepted this assignment.")
    token = notifications.issue_token(ack)
    ack.reminder_sent_at = None
    ack._audit_action = "ack_resent"
    notifications.send_acknowledgement(assignment, token)
    return token


def check_in(asset: Asset, user: User, *, condition: str, notes: str | None = None) -> Assignment:
    """FR-ASN-07: back to stock, or into repair when returned damaged."""
    assignment = open_assignment(asset)
    if assignment is None:
        raise LifecycleError(f"{asset.asset_tag} is not checked out.")
    if asset.status == S.IN_REPAIR:
        raise LifecycleError("Close the open repair before checking this asset in.")
    assignment.checked_in_at = utcnow()
    assignment.checked_in_by_id = user.id
    assignment.return_condition = condition
    assignment.notes = "\n".join(filter(None, [assignment.notes, notes])) or None
    assignment._audit_action = "check_in"
    who = assignment.employee.audit_label()
    asset._audit_employee_id = assignment.employee_id
    if condition == "Damaged":
        _transition(asset, S.IN_REPAIR, "check_in", f"Returned damaged by {who}")
        db.session.add(Repair(asset=asset, reported_at=date.today(), repair_type="Internal",
                              issue=f"Returned damaged at check-in. {notes or ''}".strip()))
    else:
        _transition(asset, S.IN_STOCK, "check_in", f"Returned by {who} ({condition})")
    return assignment


def start_repair(asset: Asset, *, issue: str, repair_type: str, vendor_id: int | None = None,
                 rma_number: str | None = None, reported_at: date | None = None) -> Repair:
    """FR-MNT-01."""
    if not issue.strip():
        raise LifecycleError("Describe the issue.")
    _transition(asset, S.IN_REPAIR, "repair_opened", issue[:200])
    repair = Repair(asset=asset, issue=issue, repair_type=repair_type, vendor_id=vendor_id,
                    rma_number=rma_number, reported_at=reported_at or date.today())
    db.session.add(repair)
    return repair


def close_repair(repair: Repair, *, outcome: str, resolution: str | None = None,
                 cost: Decimal | None = None, completed_at: date | None = None) -> bool:
    """FR-MNT-02. Returns True when the outcome means the asset should be retired."""
    if not repair.is_open:
        raise LifecycleError("This repair is already closed.")
    repair.completed_at = completed_at or date.today()
    repair.outcome = outcome
    repair.resolution = resolution
    repair.cost = cost
    repair._audit_action = "repair_closed"
    asset = repair.asset
    back_to = S.ASSIGNED if open_assignment(asset) else S.IN_STOCK
    _transition(asset, back_to, "repair_closed", f"Repair closed: {outcome}")
    return outcome == "Beyond repair"


def retire(asset: Asset, *, reason: str, retired_on: date | None = None, notes: str | None = None) -> Disposal:
    """FR-LC-02/03: checked-in assets only; any open repair is closed as beyond repair."""
    if open_assignment(asset):
        raise LifecycleError(f"Check {asset.asset_tag} in before retiring it.")
    if not reason:
        raise LifecycleError("A retirement reason is required.")
    repair = open_repair(asset)
    if repair:
        repair.completed_at = retired_on or date.today()
        repair.outcome = "Beyond repair"
    _transition(asset, S.RETIRED, "retire", reason)
    disposal = Disposal(asset=asset, retired_at=retired_on or date.today(),
                        retire_reason=reason, retire_notes=notes)
    db.session.add(disposal)
    return disposal


def dispose(asset: Asset, *, method: str, disposed_on: date | None = None, recipient: str | None = None,
            wipe_method: str | None = None, wipe_confirmed: bool = False,
            sale_value: Decimal | None = None) -> Disposal:
    """FR-LC-04. Disposed assets become read-only (FR-LC-05)."""
    if not wipe_confirmed:
        raise LifecycleError("Confirm the data wipe before disposing of an asset.")
    if not method:
        raise LifecycleError("A disposal method is required.")
    disposal = asset.disposal
    if disposal is None:
        raise LifecycleError(f"{asset.asset_tag} must be retired before disposal.")
    _transition(asset, S.DISPOSED, "dispose", method)
    disposal.disposed_at = disposed_on or date.today()
    disposal.method = method
    disposal.recipient = recipient
    disposal.data_wipe_method = wipe_method
    disposal.data_wipe_confirmed = True
    disposal.sale_value = sale_value
    return disposal


def reinstate(asset: Asset, user: User) -> None:
    """Retired -> In Stock, Admin only."""
    if not user.is_admin:
        raise LifecycleError("Only an Admin can reinstate a retired asset.")
    _transition(asset, S.IN_STOCK, "reinstate", "Reinstated to stock")
    if asset.disposal:
        db.session.delete(asset.disposal)
