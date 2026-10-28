"""Asset list, detail, create and lifecycle actions (spec §3.4 - §3.7)."""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_, select

from ..audit import timeline_filter
from ..extensions import db
from ..models import (
    CONDITIONS,
    DISPOSAL_METHODS,
    REPAIR_OUTCOMES,
    REPAIR_TYPES,
    RETIRE_REASONS,
    WIPE_METHODS,
    Asset,
    AssetModel,
    AssetStatus,
    Assignment,
    AuditLog,
    Category,
    Employee,
    Location,
    Manufacturer,
    Repair,
    Vendor,
)
from ..services import depreciation, lifecycle
from ..services.notifications import ack_link
from ..utils import csv_response, paginate, parse_date, parse_decimal

bp = Blueprint("assets", __name__, url_prefix="/assets")

SORTS = {
    "tag": Asset.asset_tag,
    "model": AssetModel.name,
    "status": Asset.status,
    "location": Location.name,
    "purchased": Asset.purchase_date,
    "warranty": Asset.warranty_end_date,
    "cost": Asset.purchase_cost,
}


def _filtered_query():
    """FR-AST-05 search and filters; disposed assets are hidden unless asked for (FR-LC-05)."""
    args = request.args
    stmt = (
        select(Asset)
        .join(AssetModel, Asset.model_id == AssetModel.id)
        .join(Manufacturer, AssetModel.manufacturer_id == Manufacturer.id)
        .outerjoin(Location, Asset.location_id == Location.id)
        .outerjoin(Assignment, (Assignment.asset_id == Asset.id) & Assignment.checked_in_at.is_(None))
        .outerjoin(Employee, Assignment.employee_id == Employee.id)
        .where(Asset.deleted_at.is_(None))
    )
    if q := args.get("q", "").strip():
        like = f"%{q}%"
        stmt = stmt.where(or_(Asset.asset_tag.ilike(like), Asset.serial_number.ilike(like),
                              AssetModel.name.ilike(like), Manufacturer.name.ilike(like),
                              Employee.full_name.ilike(like)))
    status = args.get("status", "")
    if status:
        stmt = stmt.where(Asset.status == status)
    else:
        stmt = stmt.where(Asset.status != AssetStatus.DISPOSED)
    if category := args.get("category", type=int):
        stmt = stmt.where(AssetModel.category_id == category)
    if location := args.get("location", type=int):
        stmt = stmt.where(Asset.location_id == location)
    if model := args.get("model", type=int):
        stmt = stmt.where(Asset.model_id == model)
    today = date.today()
    warranty = args.get("warranty", "")
    if warranty == "expired":
        stmt = stmt.where(Asset.warranty_end_date < today)
    elif warranty in ("30", "60", "90"):
        stmt = stmt.where(Asset.warranty_end_date.between(today, today + timedelta(days=int(warranty))))
    elif warranty == "none":
        stmt = stmt.where(Asset.warranty_end_date.is_(None))

    sort = args.get("sort", "tag")
    column = SORTS.get(sort, Asset.asset_tag)
    stmt = stmt.order_by(column.desc() if args.get("dir") == "desc" else column.asc(), Asset.id)
    return stmt


def _lookups() -> dict:
    return {
        "categories": db.session.scalars(select(Category).order_by(Category.name)).all(),
        "locations": db.session.scalars(select(Location).order_by(Location.name)).all(),
        "models": db.session.scalars(select(AssetModel).order_by(AssetModel.name)).unique().all(),
        "vendors": db.session.scalars(select(Vendor).order_by(Vendor.name)).all(),
    }


@bp.route("/")
def index():
    stmt = _filtered_query()
    if request.args.get("export") == "csv":  # FR-AST-06
        rows = []
        for a in db.session.scalars(stmt).unique():
            holder = a.open_assignment.employee.full_name if a.open_assignment else ""
            rows.append([a.asset_tag, a.model.category.name, a.model.display_name, a.serial_number,
                         a.status, a.location.name if a.location else "", holder,
                         a.purchase_date, a.purchase_cost, a.warranty_end_date])
        return csv_response("assets.csv", ["Asset tag", "Category", "Model", "Serial", "Status",
                                           "Location", "Assigned to", "Purchase date",
                                           "Purchase cost (EUR)", "Warranty end"], rows)
    page = paginate(stmt)
    return render_template("assets/list.html", page=page, statuses=AssetStatus.ALL, **_lookups())


def _next_tag() -> str:
    """FR-AST-02: next number in the configured pattern."""
    count = db.session.scalar(select(func.count()).select_from(Asset)) or 0
    pattern = current_app.config["ASSET_TAG_PATTERN"]
    n = count + 1
    while db.session.scalar(select(Asset.id).where(Asset.asset_tag == pattern.format(n))):
        n += 1
    return pattern.format(n)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = request.form
    errors: dict[str, str] = {}
    if request.method == "POST":
        tag = form.get("asset_tag", "").strip() or _next_tag()
        model = db.session.get(AssetModel, form.get("model_id", type=int) or 0)
        serial = form.get("serial_number", "").strip() or None
        if not model:
            errors["model_id"] = "Choose a model."
        if db.session.scalar(select(Asset.id).where(Asset.asset_tag == tag)):
            errors["asset_tag"] = f"Asset tag {tag} is already in use."
        if model and serial and db.session.scalar(
            select(Asset.id).join(AssetModel).where(
                Asset.serial_number == serial, AssetModel.manufacturer_id == model.manufacturer_id)
        ):
            errors["serial_number"] = f"Serial {serial} already exists for {model.manufacturer.name}."
        cost = parse_decimal(form.get("purchase_cost"))
        if form.get("purchase_cost") and cost is None:
            errors["purchase_cost"] = "Enter a number, e.g. 1299.00"
        if not errors:
            asset = Asset(
                asset_tag=tag, model=model, serial_number=serial,
                status=AssetStatus.IN_STOCK, location_id=form.get("location_id", type=int),
                purchase_date=parse_date(form.get("purchase_date")), purchase_cost=cost,
                vendor_id=form.get("vendor_id", type=int), invoice_number=form.get("invoice_number") or None,
                warranty_end_date=parse_date(form.get("warranty_end_date")), notes=form.get("notes") or None,
            )
            db.session.add(asset)
            db.session.commit()
            flash(f"Asset {asset.asset_tag} created.", "success")
            return redirect(url_for("assets.detail", asset_id=asset.id))
    return render_template("assets/form.html", form=form, errors=errors, next_tag=_next_tag(), **_lookups())


@bp.route("/<int:asset_id>")
def detail(asset_id: int):
    asset = db.session.get(Asset, asset_id) or abort(404)
    as_at = parse_date(request.args.get("as_at")) or date.today()
    dep = depreciation.for_asset(asset, as_at)
    history = db.session.scalars(
        select(AuditLog).where(AuditLog.asset_id == asset.id, timeline_filter())
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    ).all()
    employees = db.session.scalars(
        select(Employee).where(Employee.status == "ACTIVE").order_by(Employee.full_name)
    ).unique().all()
    repair_cost = sum((r.cost or 0) for r in asset.repairs)
    gain_loss = None
    if asset.disposal and asset.disposal.disposed_at and dep:
        gain_loss = (asset.disposal.sale_value or 0) - dep.book_value
    return render_template(
        "assets/detail.html", asset=asset, dep=dep, as_at=as_at, history=history,
        employees=employees, open_repair=lifecycle.open_repair(asset), repair_cost=repair_cost,
        gain_loss=gain_loss, tab=request.args.get("tab", "details"),
        conditions=CONDITIONS, repair_types=REPAIR_TYPES, repair_outcomes=REPAIR_OUTCOMES,
        retire_reasons=RETIRE_REASONS, disposal_methods=DISPOSAL_METHODS, wipe_methods=WIPE_METHODS,
        vendors=_lookups()["vendors"],
    )


def _act(asset_id: int, action):
    """Run one lifecycle action, committing on success and flashing the rule on failure."""
    asset = db.session.get(Asset, asset_id) or abort(404)
    try:
        message = action(asset)
        db.session.commit()
        flash(message, "success")
    except lifecycle.LifecycleError as err:
        db.session.rollback()
        flash(str(err), "danger")
    return redirect(url_for("assets.detail", asset_id=asset_id, tab=request.form.get("tab", "details")))


@bp.post("/<int:asset_id>/checkout")
def checkout(asset_id: int):
    def run(asset):
        employee = db.session.get(Employee, request.form.get("employee_id", type=int) or 0)
        if not employee:
            raise lifecycle.LifecycleError("Choose an employee.")
        _, token = lifecycle.check_out(
            asset, employee, current_user, expected_return=parse_date(request.form.get("expected_return")),
            condition=request.form.get("condition", "Good"), notes=request.form.get("notes") or None)
        flash(f"Demo: no SMTP configured, so here is the acknowledgement link emailed to "
              f"{employee.email}: {ack_link(token)}", "info")
        return f"{asset.asset_tag} checked out to {employee.full_name}."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/checkin")
def checkin(asset_id: int):
    def run(asset):
        a = lifecycle.check_in(asset, current_user, condition=request.form.get("condition", "Good"),
                               notes=request.form.get("notes") or None)
        return f"{asset.asset_tag} checked in from {a.employee.full_name}; now {asset.status}."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/assignments/<int:assignment_id>/resend")
def resend_ack(asset_id: int, assignment_id: int):
    def run(asset):
        assignment = db.session.get(Assignment, assignment_id)
        if not assignment or assignment.asset_id != asset.id:
            abort(404)
        token = lifecycle.resend_acknowledgement(assignment)
        flash(f"Demo acknowledgement link: {ack_link(token)}", "info")
        return f"Acknowledgement link resent to {assignment.employee.email}."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/repair")
def repair_open(asset_id: int):
    def run(asset):
        lifecycle.start_repair(asset, issue=request.form.get("issue", ""),
                               repair_type=request.form.get("repair_type", "Internal"),
                               vendor_id=request.form.get("vendor_id", type=int),
                               rma_number=request.form.get("rma_number") or None)
        return f"Repair opened; {asset.asset_tag} is In Repair."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/repairs/<int:repair_id>/close")
def repair_close(asset_id: int, repair_id: int):
    def run(asset):
        repair = db.session.get(Repair, repair_id)
        if not repair or repair.asset_id != asset.id:
            abort(404)
        beyond = lifecycle.close_repair(repair, outcome=request.form.get("outcome", "Fixed"),
                                        resolution=request.form.get("resolution") or None,
                                        cost=parse_decimal(request.form.get("cost")))
        if beyond:
            flash("Outcome was Beyond repair: retire this asset from the Lifecycle actions.", "warning")
        return f"Repair closed; {asset.asset_tag} is {asset.status}."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/retire")
def retire(asset_id: int):
    def run(asset):
        lifecycle.retire(asset, reason=request.form.get("reason", ""),
                         retired_on=parse_date(request.form.get("retired_on")),
                         notes=request.form.get("notes") or None)
        return f"{asset.asset_tag} retired."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/dispose")
def dispose(asset_id: int):
    def run(asset):
        lifecycle.dispose(asset, method=request.form.get("method", ""),
                          disposed_on=parse_date(request.form.get("disposed_on")),
                          recipient=request.form.get("recipient") or None,
                          wipe_method=request.form.get("wipe_method") or None,
                          wipe_confirmed=request.form.get("wipe_confirmed") == "on",
                          sale_value=parse_decimal(request.form.get("sale_value")))
        return f"{asset.asset_tag} disposed. The record is now read-only."
    return _act(asset_id, run)


@bp.post("/<int:asset_id>/reinstate")
def reinstate(asset_id: int):
    def run(asset):
        lifecycle.reinstate(asset, current_user)
        return f"{asset.asset_tag} reinstated to stock."
    return _act(asset_id, run)
