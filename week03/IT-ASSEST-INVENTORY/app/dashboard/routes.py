"""Dashboard widgets (spec §3.11)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, render_template
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    AckStatus,
    Asset,
    AssetModel,
    AssetStatus,
    Assignment,
    AuditLog,
    Category,
    Location,
)
from ..services import depreciation
from ..services.notifications import low_stock_models

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    today = date.today()
    by_status = dict(db.session.execute(
        select(Asset.status, func.count()).group_by(Asset.status)
    ).all())
    status_cards = [(s, by_status.get(s, 0)) for s in AssetStatus.ALL]

    active = Asset.status.in_(AssetStatus.ACTIVE)
    by_location = db.session.execute(
        select(Location.name, func.count(Asset.id)).join(Asset, Asset.location_id == Location.id)
        .where(active).group_by(Location.name).order_by(func.count(Asset.id).desc())
    ).all()
    by_category = db.session.execute(
        select(Category.name, func.count(Asset.id))
        .join(AssetModel, AssetModel.category_id == Category.id)
        .join(Asset, Asset.model_id == AssetModel.id)
        .where(active).group_by(Category.name).order_by(func.count(Asset.id).desc())
    ).all()

    warranty = {}
    for days in (30, 60, 90):
        warranty[days] = db.session.scalar(
            select(func.count()).select_from(Asset).where(
                active, Asset.warranty_end_date >= today,
                Asset.warranty_end_date <= today + timedelta(days=days))
        )
    expiring_soon = db.session.scalars(
        select(Asset).where(active, Asset.warranty_end_date >= today,
                            Asset.warranty_end_date <= today + timedelta(days=30))
        .order_by(Asset.warranty_end_date).limit(8)
    ).all()

    open_assignments = db.session.scalars(
        select(Assignment).where(Assignment.checked_in_at.is_(None))
        .options(selectinload(Assignment.asset))
    ).unique().all()
    pending_acks = [a for a in open_assignments
                    if a.acknowledgement and a.acknowledgement.effective_status in
                    (AckStatus.PENDING, AckStatus.DISPUTED, AckStatus.EXPIRED)]
    overdue = [a for a in open_assignments if a.is_overdue(today)]

    total_book = Decimal(0)
    for asset in db.session.scalars(select(Asset).where(active)).unique():
        dep = depreciation.for_asset(asset, today)
        if dep:
            total_book += dep.book_value

    recent = db.session.scalars(
        select(AuditLog).where(AuditLog.entity_type == "asset")
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(8)
    ).all()

    return render_template(
        "dashboard.html",
        status_cards=status_cards,
        by_location=by_location,
        by_category=by_category,
        warranty=warranty,
        expiring_soon=expiring_soon,
        pending_acks=sorted(pending_acks, key=lambda a: a.checked_out_at)[:8],
        pending_count=len(pending_acks),
        overdue=overdue[:8],
        overdue_count=len(overdue),
        low_stock=low_stock_models(),
        total_book=total_book,
        recent=recent,
    )
