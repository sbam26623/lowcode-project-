"""Build the standalone HTML prototype from the seeded database.

    python prototype/build.py        (after `flask --app app:create_app seed`)

Reads instance/inventory.db through the app models, embeds a compact JSON snapshot into
prototype/template.html and writes prototype/index.html.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Asset,
    AssetModel,
    Assignment,
    AuditLog,
    Category,
    Department,
    Employee,
    Location,
    Repair,
    User,
    Vendor,
)


def iso(value):
    return value.isoformat() if value else None


def money(value):
    return float(value) if value is not None else None


def snapshot() -> dict:
    s = db.session
    users = {u.id: u.full_name for u in s.scalars(select(User))}
    tags = dict(s.execute(select(Asset.id, Asset.asset_tag)).all())
    return {
        "today": date.today().isoformat(),
        "org": "Nordwind Logistik GmbH",
        "categories": [{"id": c.id, "name": c.name, "life": c.default_useful_life_months,
                        "residual": float(c.default_residual_pct)} for c in s.scalars(select(Category))],
        "locations": [{"id": l.id, "name": l.name, "address": l.address, "city": l.city}
                      for l in s.scalars(select(Location))],
        "departments": [{"id": d.id, "name": d.name} for d in s.scalars(select(Department))],
        "vendors": [{"id": v.id, "name": v.name} for v in s.scalars(select(Vendor))],
        "models": [{"id": m.id, "name": m.name, "maker": m.manufacturer.name, "categoryId": m.category_id,
                    "number": m.model_number, "threshold": m.low_stock_threshold}
                   for m in s.scalars(select(AssetModel)).unique()],
        "employees": [{"id": e.id, "code": e.employee_code, "name": e.full_name, "email": e.email,
                       "departmentId": e.department_id, "locationId": e.location_id, "managerId": e.manager_id,
                       "status": e.status, "leaving": iso(e.leaving_date)}
                      for e in s.scalars(select(Employee)).unique()],
        "assets": [{"id": a.id, "tag": a.asset_tag, "modelId": a.model_id, "serial": a.serial_number,
                    "status": a.status, "locationId": a.location_id, "purchased": iso(a.purchase_date),
                    "cost": money(a.purchase_cost), "vendorId": a.vendor_id, "invoice": a.invoice_number,
                    "warranty": iso(a.warranty_end_date), "custom": a.custom_fields or {},
                    "disposal": None if not a.disposal else {
                        "retired": iso(a.disposal.retired_at), "reason": a.disposal.retire_reason,
                        "disposed": iso(a.disposal.disposed_at), "method": a.disposal.method,
                        "recipient": a.disposal.recipient, "wipe": a.disposal.data_wipe_method,
                        "wipeConfirmed": a.disposal.data_wipe_confirmed, "sale": money(a.disposal.sale_value)}}
                   for a in s.scalars(select(Asset).order_by(Asset.id)).unique()],
        "assignments": [{"id": a.id, "assetId": a.asset_id, "employeeId": a.employee_id,
                         "out": iso(a.checked_out_at), "expected": iso(a.expected_return_date),
                         "condOut": a.checkout_condition, "in": iso(a.checked_in_at), "condIn": a.return_condition,
                         "ack": None if not a.acknowledgement else {
                             "status": a.acknowledgement.effective_status, "sent": iso(a.acknowledgement.sent_at),
                             "responded": iso(a.acknowledgement.responded_at),
                             "typed": a.acknowledgement.typed_name, "comment": a.acknowledgement.comment}}
                        for a in s.scalars(select(Assignment).order_by(Assignment.id)).unique()],
        "repairs": [{"id": r.id, "assetId": r.asset_id, "reported": iso(r.reported_at), "issue": r.issue,
                     "type": r.repair_type, "completed": iso(r.completed_at), "outcome": r.outcome,
                     "resolution": r.resolution, "cost": money(r.cost)}
                    for r in s.scalars(select(Repair).order_by(Repair.id))],
        "audit": [{"at": iso(e.occurred_at), "user": users.get(e.user_id), "type": e.entity_type,
                   "label": tags.get(e.asset_id, e.entity_label), "action": e.action, "note": e.note, "assetId": e.asset_id,
                   "employeeId": e.employee_id, "changes": e.changes if e.action != "create" else None}
                  for e in s.scalars(select(AuditLog).where(AuditLog.entity_type.in_(["asset", "assignment"]))
                                     .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()))],
    }


def main() -> None:
    app = create_app()
    with app.app_context():
        data = snapshot()
    here = Path(__file__).resolve().parent
    template = (here / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = here / "index.html"
    out.write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(data['assets'])} assets)")


if __name__ == "__main__":
    main()
