from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import AckStatus, AssetStatus, AuditLog, EmailLog
from app.services import depreciation, lifecycle


def test_straight_line_matches_manual_calculation():
    # (1200 - 120) / 36 = 30.00 per month; 21 whole months by 2026-10-28.
    dep = depreciation.calculate(Decimal("1200"), date(2025, 1, 15), 36, Decimal("10"), date(2026, 10, 28))
    assert dep.monthly == Decimal("30.00")
    assert dep.months_elapsed == 21
    assert dep.accumulated == Decimal("630.00")
    assert dep.book_value == Decimal("570.00")


def test_book_value_never_below_residual_and_stops_at_disposal():
    late = depreciation.calculate(Decimal("1000"), date(2018, 1, 1), 36, Decimal("10"), date(2026, 1, 1))
    assert late.book_value == Decimal("100.00")
    stopped = depreciation.calculate(Decimal("1200"), date(2025, 1, 15), 36, Decimal("10"),
                                     date(2026, 10, 28), stop_date=date(2025, 7, 15))
    assert stopped.months_elapsed == 6


def test_months_between_counts_whole_months():
    assert depreciation.months_between(date(2025, 1, 31), date(2025, 2, 28)) == 0
    assert depreciation.months_between(date(2025, 1, 15), date(2025, 2, 15)) == 1
    assert depreciation.months_between(date(2025, 3, 1), date(2025, 1, 1)) == 0


def test_checkout_issues_ack_and_audits(app, data):
    asset, emp, mgr = data["asset"], data["employee"], data["manager"]
    with app.test_request_context():
        assignment, token = lifecycle.check_out(asset, emp, mgr)
        db.session.commit()
    assert asset.status == AssetStatus.ASSIGNED
    assert assignment.acknowledgement.status == AckStatus.PENDING
    assert token and assignment.acknowledgement.token_hash != token
    assert db.session.scalar(select(EmailLog).where(EmailLog.to_address == emp.email))
    entry = db.session.scalar(select(AuditLog).where(AuditLog.entity_type == "asset", AuditLog.action == "check_out"))
    assert entry.changes["status"] == [AssetStatus.IN_STOCK, AssetStatus.ASSIGNED]
    assert entry.asset_id == asset.id


def test_invalid_transitions_are_rejected(app, data):
    asset, emp, mgr = data["asset"], data["employee"], data["manager"]
    with app.test_request_context():
        lifecycle.check_out(asset, emp, mgr)
        with pytest.raises(lifecycle.LifecycleError, match="Check IT-000001 in"):
            lifecycle.retire(asset, reason="End of life")
        with pytest.raises(lifecycle.LifecycleError, match="Only In Stock"):
            lifecycle.check_out(asset, emp, mgr)
        lifecycle.check_in(asset, mgr, condition="Good")
        with pytest.raises(lifecycle.LifecycleError, match="must be retired"):
            lifecycle.dispose(asset, method="Recycled", wipe_confirmed=True)


def test_damaged_checkin_goes_to_repair_and_back_to_stock(app, data):
    asset, emp, mgr = data["asset"], data["employee"], data["manager"]
    with app.test_request_context():
        lifecycle.check_out(asset, emp, mgr)
        lifecycle.check_in(asset, mgr, condition="Damaged")
        db.session.flush()
        assert asset.status == AssetStatus.IN_REPAIR
        beyond = lifecycle.close_repair(lifecycle.open_repair(asset), outcome="Fixed")
    assert not beyond and asset.status == AssetStatus.IN_STOCK


def test_retire_dispose_and_admin_only_reinstate(app, data):
    asset, mgr, admin = data["asset"], data["manager"], data["admin"]
    lifecycle.retire(asset, reason="End of life")
    with pytest.raises(lifecycle.LifecycleError, match="Only an Admin"):
        lifecycle.reinstate(asset, mgr)
    with pytest.raises(lifecycle.LifecycleError, match="data wipe"):
        lifecycle.dispose(asset, method="Recycled")
    lifecycle.reinstate(asset, admin)
    assert asset.status == AssetStatus.IN_STOCK


def test_audit_log_is_append_only(app, data):
    db.session.commit()
    entry = db.session.scalar(select(AuditLog))
    entry.action = "tampered"
    with pytest.raises(PermissionError):
        db.session.commit()
