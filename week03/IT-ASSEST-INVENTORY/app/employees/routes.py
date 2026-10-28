"""Employees and open assignments (spec §3.3, §3.6)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, render_template, request
from sqlalchemy import func, or_, select

from ..audit import timeline_filter
from ..extensions import db
from ..models import AckStatus, Assignment, AuditLog, Department, Employee, Location
from ..utils import PAGE_SIZES, Page, csv_response

bp = Blueprint("employees", __name__)


@bp.route("/employees/")
def index():
    args = request.args
    holdings = (
        select(Assignment.employee_id, func.count().label("n"))
        .where(Assignment.checked_in_at.is_(None))
        .group_by(Assignment.employee_id)
        .subquery()
    )
    stmt = select(Employee, func.coalesce(holdings.c.n, 0)).outerjoin(
        holdings, holdings.c.employee_id == Employee.id)
    if q := args.get("q", "").strip():
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like), Employee.email.ilike(like),
                              Employee.employee_code.ilike(like)))
    if dept := args.get("department", type=int):
        stmt = stmt.where(Employee.department_id == dept)
    if loc := args.get("location", type=int):
        stmt = stmt.where(Employee.location_id == loc)
    if status := args.get("status"):
        stmt = stmt.where(Employee.status == status)
    stmt = stmt.order_by(Employee.full_name)

    per_page = request.args.get("per_page", 25, type=int)
    per_page = per_page if per_page in PAGE_SIZES else 25
    page_no = max(request.args.get("page", 1, type=int), 1)
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.session.execute(stmt.limit(per_page).offset((page_no - 1) * per_page)).unique().all()
    page = Page(items=rows, page=page_no, per_page=per_page, total=total)
    return render_template(
        "employees/list.html", page=page,
        departments=db.session.scalars(select(Department).order_by(Department.name)).all(),
        locations=db.session.scalars(select(Location).order_by(Location.name)).all(),
    )


@bp.route("/employees/<int:employee_id>")
def detail(employee_id: int):
    employee = db.session.get(Employee, employee_id) or abort(404)
    assignments = db.session.scalars(
        select(Assignment).where(Assignment.employee_id == employee.id)
        .order_by(Assignment.checked_out_at.desc())
    ).unique().all()
    history = db.session.scalars(
        select(AuditLog).where(AuditLog.employee_id == employee.id, timeline_filter())
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    ).all()
    current = [a for a in assignments if a.is_open]
    return render_template("employees/detail.html", employee=employee, current=current,
                           assignments=assignments, history=history)


@bp.route("/employees/<int:employee_id>/checklist")
def checklist(employee_id: int):
    """FR-EMP-05 printable leaver return checklist."""
    employee = db.session.get(Employee, employee_id) or abort(404)
    current = db.session.scalars(
        select(Assignment).where(Assignment.employee_id == employee.id, Assignment.checked_in_at.is_(None))
    ).unique().all()
    return render_template("employees/checklist.html", employee=employee, current=current)


@bp.route("/assignments/")
def assignments():
    """Open assignments with acknowledgement status and overdue flag."""
    today = date.today()
    ack = request.args.get("ack", "")
    overdue_only = request.args.get("overdue") == "1"
    rows = db.session.scalars(
        select(Assignment).where(Assignment.checked_in_at.is_(None))
        .order_by(Assignment.checked_out_at.desc())
    ).unique().all()
    if ack:
        rows = [a for a in rows if a.acknowledgement and a.acknowledgement.effective_status == ack]
    if overdue_only:
        rows = [a for a in rows if a.is_overdue(today)]
    if request.args.get("export") == "csv":
        return csv_response("assignments.csv",
                            ["Asset tag", "Model", "Employee", "Checked out", "Expected return",
                             "Acknowledgement", "Overdue"],
                            [[a.asset.asset_tag, a.asset.model.display_name, a.employee.full_name,
                              a.checked_out_at.date(), a.expected_return_date,
                              a.acknowledgement.effective_status if a.acknowledgement else "",
                              "yes" if a.is_overdue(today) else ""] for a in rows])
    return render_template("assignments/list.html", rows=rows, ack_statuses=AckStatus.ALL,
                           ack=ack, overdue_only=overdue_only)
