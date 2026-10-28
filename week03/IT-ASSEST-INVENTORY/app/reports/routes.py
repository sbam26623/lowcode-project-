"""Reports (spec §3.11) and the audit log viewer (§3.12)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from flask import Blueprint, abort, render_template, request
from sqlalchemy import select

from ..audit import log_event
from ..extensions import db
from ..models import Asset, AssetStatus, Assignment, AuditLog, Employee, User
from ..services import depreciation
from ..utils import csv_response, paginate, parse_date

bp = Blueprint("reports", __name__)


@dataclass
class Report:
    code: str
    title: str
    description: str
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    totals: list | None = None
    money_cols: set[int] = field(default_factory=set)
    link_col: int | None = None  # column holding an asset id to link the first cell
    params: dict = field(default_factory=dict)


def _active_assets() -> list[Asset]:
    return db.session.scalars(
        select(Asset).where(Asset.status.in_(AssetStatus.ACTIVE), Asset.deleted_at.is_(None))
    ).unique().all()


def rpt01_inventory() -> Report:
    group = request.args.get("group", "location")
    r = Report("RPT-01", "Inventory by status / location / category",
               "Asset counts per group and status (disposed assets excluded).", params={"group": group})
    statuses = [s for s in AssetStatus.ALL if s != AssetStatus.DISPOSED]
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in db.session.scalars(select(Asset).where(Asset.status != AssetStatus.DISPOSED)).unique():
        key = {"location": a.location.name if a.location else "—",
               "category": a.model.category.name,
               "model": a.model.display_name}.get(group, a.status)
        counts[key][a.status] += 1
    r.columns = [group.title()] + statuses + ["Total"]
    for key in sorted(counts):
        row = [counts[key][s] for s in statuses]
        r.rows.append([key, *row, sum(row)])
    r.totals = ["Total"] + [sum(row[i + 1] for row in r.rows) for i in range(len(statuses) + 1)]
    return r


def rpt02_by_employee() -> Report:
    leavers = request.args.get("leavers") == "1"
    r = Report("RPT-02", "Assets by employee",
               "Current holdings per employee. Tick 'leavers only' for leavers still holding assets.",
               params={"leavers": leavers})
    r.columns = ["Employee", "Code", "Department", "Location", "Status", "Leaving date", "Assets", "Asset tags"]
    held: dict[int, list[Assignment]] = defaultdict(list)
    for a in db.session.scalars(select(Assignment).where(Assignment.checked_in_at.is_(None))).unique():
        held[a.employee_id].append(a)
    employees = db.session.scalars(select(Employee).order_by(Employee.full_name)).unique().all()
    for e in employees:
        items = held.get(e.id, [])
        if not items or (leavers and not e.is_leaver):
            continue
        r.rows.append([e.full_name, e.employee_code, e.department.name if e.department else "",
                       e.location.name if e.location else "", "Leaver" if e.is_leaver else "Active",
                       e.leaving_date, len(items), ", ".join(a.asset.asset_tag for a in items)])
    r.totals = ["Total", "", "", "", "", "", sum(row[6] for row in r.rows), ""]
    return r


def rpt03_warranty() -> Report:
    days = request.args.get("days", 90, type=int)
    bucket = request.args.get("bucket", "")
    today = date.today()
    r = Report("RPT-03", "Warranty status",
               "Active assets whose warranty has expired, expires within N days, or was never recorded.",
               params={"days": days, "bucket": bucket}, link_col=7)
    r.columns = ["Asset tag", "Model", "Status", "Location", "Warranty end", "Days left", "Bucket"]
    for a in sorted(_active_assets(), key=lambda a: (a.warranty_end_date or date.max)):
        if a.warranty_end_date is None:
            b, left = "No warranty", None
        elif a.warranty_end_date < today:
            b, left = "Expired", (a.warranty_end_date - today).days
        elif a.warranty_end_date <= today + timedelta(days=days):
            b, left = f"Expiring ≤ {days} days", (a.warranty_end_date - today).days
        else:
            continue
        if bucket and not b.startswith(bucket):
            continue
        r.rows.append([a.asset_tag, a.model.display_name, a.status, a.location.name if a.location else "",
                       a.warranty_end_date, left, b, a.id])
    return r


AGE_BANDS = ["0–1 y", "1–2 y", "2–3 y", "3–4 y", "4+ y"]


def rpt04_aging() -> Report:
    today = date.today()
    r = Report("RPT-04", "Asset aging / refresh planning",
               "Active assets per category by age since purchase, and how many are past their useful life.")
    r.columns = ["Category"] + AGE_BANDS + ["Total", "Past useful life", "Replacement cost"]
    r.money_cols = {8}
    bands: dict[str, list[int]] = defaultdict(lambda: [0] * 5)
    past: dict[str, int] = defaultdict(int)
    replace_cost: dict[str, Decimal] = defaultdict(Decimal)
    for a in _active_assets():
        if not a.purchase_date:
            continue
        cat = a.model.category.name
        months = depreciation.months_between(a.purchase_date, today)
        bands[cat][min(months // 12, 4)] += 1
        if months >= a.life_months:
            past[cat] += 1
            replace_cost[cat] += a.purchase_cost or 0
    for cat in sorted(bands):
        r.rows.append([cat, *bands[cat], sum(bands[cat]), past[cat], replace_cost[cat]])
    r.totals = ["Total"] + [sum(row[i] for row in r.rows) for i in range(1, 9)]
    return r


def rpt05_financial() -> Report:
    as_at = parse_date(request.args.get("as_at")) or date.today()
    group = request.args.get("group", "category")
    r = Report("RPT-05", "Depreciation / financial",
               "Straight-line book value of active assets as at a date; purchases in the 12 months before it.",
               params={"as_at": as_at, "group": group})
    r.columns = [group.title(), "Assets", "Total cost", "Accumulated depreciation", "Book value",
                 "Purchased (last 12 mo)", "Purchases value (last 12 mo)"]
    r.money_cols = {2, 3, 4, 6}
    agg: dict[str, list] = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0), 0, Decimal(0)])
    year_ago = as_at - timedelta(days=365)
    for a in _active_assets():
        if not a.purchase_date or a.purchase_date > as_at:
            continue
        dep = depreciation.for_asset(a, as_at)
        if not dep:
            continue
        key = a.location.name if group == "location" and a.location else a.model.category.name
        g = agg[key]
        g[0] += 1
        g[1] += dep.cost
        g[2] += dep.accumulated
        g[3] += dep.book_value
        if a.purchase_date > year_ago:
            g[4] += 1
            g[5] += dep.cost
    for key in sorted(agg):
        r.rows.append([key, *agg[key]])
    r.totals = ["Total"] + [sum(row[i] for row in r.rows) for i in range(1, 7)]
    return r


def rpt08_disposals() -> Report:
    r = Report("RPT-08", "Disposal register",
               "Retired and disposed assets with method, date and data-wipe confirmation.", link_col=11)
    r.columns = ["Asset tag", "Model", "Status", "Retired", "Reason", "Disposed", "Method",
                 "Recipient", "Data wipe", "Wipe confirmed", "Sale value"]
    r.money_cols = {10}
    assets = db.session.scalars(
        select(Asset).where(Asset.status.in_([AssetStatus.RETIRED, AssetStatus.DISPOSED]))
    ).unique().all()
    for a in sorted(assets, key=lambda a: a.disposal.retired_at if a.disposal else date.min, reverse=True):
        d = a.disposal
        if not d:
            continue
        r.rows.append([a.asset_tag, a.model.display_name, a.status, d.retired_at, d.retire_reason,
                       d.disposed_at, d.method or "", d.recipient or "", d.data_wipe_method or "",
                       "Yes" if d.data_wipe_confirmed else "No", d.sale_value, a.id])
    return r


REPORTS = {
    "inventory": rpt01_inventory,
    "by-employee": rpt02_by_employee,
    "warranty": rpt03_warranty,
    "aging": rpt04_aging,
    "financial": rpt05_financial,
    "disposals": rpt08_disposals,
}


CATALOGUE = [
    ("inventory", "RPT-01", "Inventory by status / location / category", "Counts per site, category or model."),
    ("by-employee", "RPT-02", "Assets by employee", "Who holds what; leavers with outstanding assets."),
    ("warranty", "RPT-03", "Warranty status", "Expired, expiring within N days, no warranty."),
    ("aging", "RPT-04", "Asset aging / refresh planning", "Age bands per category; past useful life."),
    ("financial", "RPT-05", "Depreciation / financial", "Cost, accumulated depreciation, book value as at a date."),
    ("disposals", "RPT-08", "Disposal register", "Retired/disposed assets with data-wipe confirmation."),
]


@bp.route("/reports/")
def index():
    return render_template("reports/index.html", catalogue=CATALOGUE)


@bp.route("/reports/<slug>")
def show(slug: str):
    fn = REPORTS.get(slug) or abort(404)
    report = fn()
    if request.args.get("export") == "csv":
        width = len(report.columns)
        rows = [row[:width] for row in report.rows] + ([report.totals] if report.totals else [])
        log_event("export", entity_type="report", label=report.code)
        db.session.commit()
        return csv_response(f"{report.code.lower()}-{slug}.csv", report.columns, rows)
    return render_template("reports/show.html", report=report, slug=slug)


@bp.route("/audit/")
def audit():
    """FR-AUD-04: filterable, exportable audit log."""
    args = request.args
    stmt = select(AuditLog)
    if start := parse_date(args.get("from")):
        stmt = stmt.where(AuditLog.occurred_at >= datetime.combine(start, time.min))
    if end := parse_date(args.get("to")):
        stmt = stmt.where(AuditLog.occurred_at < datetime.combine(end + timedelta(days=1), time.min))
    if user_id := args.get("user", type=int):
        stmt = stmt.where(AuditLog.user_id == user_id)
    if entity := args.get("entity"):
        stmt = stmt.where(AuditLog.entity_type == entity)
    if action := args.get("action"):
        stmt = stmt.where(AuditLog.action == action)
    if q := args.get("q", "").strip():
        stmt = stmt.where(AuditLog.entity_label.ilike(f"%{q}%"))
    stmt = stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    if args.get("export") == "csv":
        rows = [[e.occurred_at.isoformat(timespec="seconds") + "Z", e.user.email if e.user else "system",
                 e.ip_address or "", e.entity_type, e.entity_id, e.entity_label, e.action, e.note or "",
                 e.changes or ""] for e in db.session.scalars(stmt)]
        return csv_response("audit-log.csv", ["Occurred (UTC)", "User", "IP", "Entity", "Entity ID",
                                              "Label", "Action", "Note", "Changes"], rows)
    page = paginate(stmt)
    entities = db.session.scalars(select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)).all()
    actions = db.session.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()
    users = db.session.scalars(select(User).order_by(User.full_name)).all()
    return render_template("audit/list.html", page=page, entities=entities, actions=actions, users=users)
