"""Random demo data: a fictional German company with four sites (run ``flask seed``).

Everything here is invented. Demo sign-ins (local development only):
    admin@nordwind.example    / DEMO_PASSWORD   (Admin)
    manager@nordwind.example  / DEMO_PASSWORD   (IT Asset Manager)
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from faker import Faker

from .auth.routes import hash_password
from .extensions import db
from .models import (
    Acknowledgement,
    AckStatus,
    Asset,
    AssetModel,
    AssetStatus,
    Assignment,
    AuditLog,
    Category,
    Department,
    Disposal,
    Employee,
    Location,
    Manufacturer,
    Repair,
    Role,
    User,
    Vendor,
    utcnow,
)

DEMO_PASSWORD = "nordwind-demo-2026"

LOCATIONS = [
    ("Berlin HQ", "Friedrichstraße 120", "Berlin"),
    ("Munich Office", "Leopoldstraße 45", "München"),
    ("Hamburg Office", "Am Sandtorkai 12", "Hamburg"),
    ("Frankfurt Office", "Mainzer Landstraße 77", "Frankfurt am Main"),
]
LOCATION_WEIGHTS = [45, 22, 18, 15]
DEPARTMENTS = ["Engineering", "Finance", "Sales", "Marketing", "Human Resources", "Operations",
               "Customer Support", "IT"]
# Open question 1 answered: spec defaults (36/60/24 months), 10 % residual.
CATEGORIES = [("Laptop", 36), ("Desktop", 36), ("Monitor", 60), ("Phone", 24), ("Tablet", 24),
              ("Docking Station", 36), ("Peripheral", 36), ("Other", 36)]
# (manufacturer, model, model number, category, list price EUR, low-stock threshold, serial prefix)
MODELS = [
    ("Dell", "Latitude 7450", "LAT7450", "Laptop", 1449, 5, "DL"),
    ("Lenovo", "ThinkPad T14 Gen 5", "21ML", "Laptop", 1329, 5, "PF"),
    ("Apple", "MacBook Pro 14 (M4)", "MX2E3D/A", "Laptop", 2299, 2, "C02"),
    ("HP", "EliteBook 840 G11", "9G0F3ET", "Laptop", 1389, 3, "5CG"),
    ("Dell", "OptiPlex 7020 Micro", "OPT7020", "Desktop", 889, None, "DO"),
    ("Dell", "UltraSharp U2724D", "U2724D", "Monitor", 479, 6, "CN0"),
    ("LG", "27UP850-W", "27UP850", "Monitor", 419, None, "LG"),
    ("Apple", "iPhone 16", "MYEV3ZD/A", "Phone", 949, 5, "F2L"),
    ("Samsung", "Galaxy S25", "SM-S931B", "Phone", 899, None, "R5C"),
    ("Apple", "iPad Air 11 (M2)", "MUWD3NF/A", "Tablet", 699, None, "DMP"),
    ("Dell", "Thunderbolt Dock WD22TB4", "WD22TB4", "Docking Station", 299, 4, "WD"),
    ("Lenovo", "ThinkPad Universal USB-C Dock", "40AY", "Docking Station", 239, None, "ZK"),
    ("Logitech", "MX Keys S", "920-011565", "Peripheral", 119, None, "LK"),
    ("Logitech", "MX Master 3S", "910-006559", "Peripheral", 99, None, "LM"),
    ("Jabra", "Evolve2 65", "26599-989", "Other", 229, 2, "JB"),
]
MODEL_WEIGHTS = [16, 14, 5, 7, 6, 14, 6, 7, 3, 3, 8, 3, 3, 3, 2]
VENDORS = [
    ("Nordlicht IT GmbH", "Jana Becker", "vertrieb@nordlicht-it.example", "+49 30 5550 1100"),
    ("Rheinwerk Systemhaus AG", "Tobias Krüger", "orders@rheinwerk-systeme.example", "+49 221 5550 2200"),
    ("Alpen Hardware KG", "Lena Huber", "service@alpen-hardware.example", "+49 89 5550 3300"),
    ("Hansa Tech Supply GmbH", "Mats Petersen", "kontakt@hansa-tech.example", "+49 40 5550 4400"),
]
ISSUES = ["Battery swelling", "Keyboard keys unresponsive", "Cracked screen", "Fan noise / overheating",
          "No power", "Dead pixels", "Charging port loose", "Docking station not detecting displays",
          "Liquid damage", "SSD failure"]
RESOLUTIONS = ["Battery replaced", "Keyboard replaced", "Display panel replaced", "Fan cleaned and thermal paste renewed",
               "Mainboard replaced under warranty", "Unit swapped by vendor", "Firmware update and reseat", "SSD replaced, reimaged"]


def _at(day: date, rng: random.Random) -> datetime:
    """A working-hours UTC timestamp on the given day, never in the future."""
    return _past(datetime.combine(day, time(rng.randint(6, 15), rng.randint(0, 59))), rng)


def _past(when: datetime, rng: random.Random) -> datetime:
    now = utcnow()
    return when if when < now else now - timedelta(minutes=rng.randint(5, 90))


def seed(n_assets: int = 320, n_employees: int = 120, rng_seed: int = 2026, today: date | None = None) -> dict:
    rng = random.Random(rng_seed)
    fake = Faker("de_DE")
    fake.seed_instance(rng_seed)
    today = today or date.today()

    db.drop_all()
    db.create_all()
    session = db.session
    session.info["skip_audit"] = True  # history below is synthesised with realistic dates

    admin = User(email="admin@nordwind.example", full_name="Katrin Vogel", role=Role.ADMIN,
                 password_hash=hash_password(DEMO_PASSWORD), mfa_enabled=True)
    manager = User(email="manager@nordwind.example", full_name="Deniz Arslan", role=Role.MANAGER,
                   password_hash=hash_password(DEMO_PASSWORD))
    manager2 = User(email="j.wagner@nordwind.example", full_name="Jonas Wagner", role=Role.MANAGER,
                    password_hash=hash_password(DEMO_PASSWORD))
    it_staff = [admin, manager, manager2]
    session.add_all(it_staff)

    locations = [Location(name=n, address=a, city=c) for n, a, c in LOCATIONS]
    departments = [Department(name=n) for n in DEPARTMENTS]
    categories = {n: Category(name=n, default_useful_life_months=life, default_residual_pct=Decimal("10"))
                  for n, life in CATEGORIES}
    manufacturers = {n: Manufacturer(name=n) for n in sorted({m[0] for m in MODELS})}
    vendors = [Vendor(name=n, contact_name=c, email=e, phone=p) for n, c, e, p in VENDORS]
    models = [AssetModel(manufacturer=manufacturers[mf], category=categories[cat], name=name,
                         model_number=num, low_stock_threshold=thr)
              for mf, name, num, cat, _, thr, _ in MODELS]
    session.add_all([*locations, *departments, *categories.values(), *manufacturers.values(), *vendors, *models])
    session.flush()

    # --- employees -----------------------------------------------------------
    employees: list[Employee] = []
    used_emails: set[str] = set()
    for i in range(n_employees):
        first, last = fake.first_name(), fake.last_name()
        email = f"{first}.{last}".lower()
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), (" ", "")):
            email = email.replace(a, b)
        while email in used_emails:
            email += str(rng.randint(1, 9))
        used_emails.add(email)
        emp = Employee(employee_code=f"E{10230 + i}", full_name=f"{first} {last}",
                       email=f"{email}@nordwind.example",
                       department=rng.choices(departments, [30, 8, 16, 8, 5, 14, 14, 5])[0],
                       location=rng.choices(locations, LOCATION_WEIGHTS)[0])
        employees.append(emp)
    session.add_all(employees)
    session.flush()
    leads = employees[:12]
    for emp in employees[12:]:
        emp.manager = rng.choice(leads)
    # Leavers: some have left with kit outstanding, some leave soon.
    leavers = rng.sample(employees[12:], 7)
    for emp, offset in zip(leavers, [-40, -18, -9, -3, 6, 14, 21]):
        emp.status = "LEAVER"
        emp.leaving_date = today + timedelta(days=offset)
    active_employees = [e for e in employees if e.status == "ACTIVE"]

    # --- assets --------------------------------------------------------------
    audit_rows: list[dict] = []

    def audit(when: datetime, entity, action: str, note: str | None = None, changes=None, *,
              by_employee: bool = False, employee: Employee | None = None):
        asset_id = entity.id if isinstance(entity, Asset) else getattr(entity, "asset_id", None)
        employee_id = employee.id if employee else getattr(entity, "employee_id", None)
        audit_rows.append(dict(occurred_at=when, user_id=None if by_employee else rng.choice(it_staff).id, ip_address=f"10.20.{rng.randint(1, 4)}.{rng.randint(10, 250)}",
                               entity_type=type(entity).__tablename__, entity_id=entity.id,
                               entity_label=entity.audit_label(), action=action, note=note, changes=changes,
                               asset_id=asset_id, employee_id=employee_id))

    assets: list[Asset] = []
    spec = {m.name: row for m, row in zip(models, MODELS)}
    for i in range(n_assets):
        model = rng.choices(models, MODEL_WEIGHTS)[0]
        _, _, _, _, price, _, prefix = spec[model.name]
        age_days = int(rng.triangular(5, 365 * 5.5, 365 * 1.6))
        purchased = today - timedelta(days=age_days)
        cost = Decimal(price) * Decimal(rng.choice(["0.92", "0.95", "0.97", "1.00", "1.00", "1.03"]))
        warranty_years = {"Laptop": 3, "Desktop": 3, "Monitor": 3, "Phone": 2, "Tablet": 1}.get(model.category.name)
        asset = Asset(
            asset_tag=f"IT-{i + 1:06d}", model=model,
            serial_number=f"{prefix}{''.join(rng.choices('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789', k=9))}",
            status=AssetStatus.IN_STOCK, location=rng.choices(locations, LOCATION_WEIGHTS)[0],
            purchase_date=purchased, purchase_cost=cost.quantize(Decimal("0.01")), vendor=rng.choice(vendors),
            invoice_number=f"RE-{purchased.year}-{rng.randint(1000, 9999)}",
            warranty_end_date=(purchased.replace(year=purchased.year + warranty_years)
                               if warranty_years and not (purchased.month == 2 and purchased.day == 29) else None)
            if rng.random() > 0.04 else None,
            created_at=_at(purchased, rng),
        )
        if model.category.name == "Laptop":
            asset.custom_fields = {"CPU": rng.choice(["Intel Core Ultra 7 165U", "Intel Core Ultra 5 135U", "AMD Ryzen 7 PRO 8840U", "Apple M4 Pro"]),
                                   "RAM": rng.choice(["16 GB", "32 GB"]), "Storage": rng.choice(["512 GB SSD", "1 TB SSD"]),
                                   "OS": "macOS 15" if model.manufacturer.name == "Apple" else "Windows 11 Pro"}
        elif model.category.name == "Phone":
            asset.custom_fields = {"IMEI": "35" + "".join(rng.choices("0123456789", k=13)),
                                   "Phone number": f"+49 15{rng.randint(1, 9)} {rng.randint(1000000, 9999999)}"}
        assets.append(asset)
    session.add_all(assets)
    session.flush()

    for asset in assets:
        audit(_at(asset.purchase_date, rng), asset, "create", "Asset registered",
              {"asset_tag": [None, asset.asset_tag], "model_id": [None, asset.model_id],
               "serial_number": [None, asset.serial_number], "purchase_cost": [None, str(asset.purchase_cost)]})

    # --- lifecycle history ---------------------------------------------------
    holder_pool = active_employees + leavers
    counts = {"assignments": 0, "repairs": 0, "disposals": 0}

    def checkout(asset: Asset, emp: Employee, when: date, *, loan: bool = False) -> Assignment:
        a = Assignment(asset=asset, employee=emp, checked_out_at=_at(when, rng),
                       checked_out_by_id=rng.choice(it_staff).id, checkout_condition="New" if when - asset.purchase_date < timedelta(days=20) else "Good",
                       expected_return_date=when + timedelta(days=rng.choice([14, 30, 45])) if loan else None)
        session.add(a)
        session.flush()
        sent = a.checked_out_at
        ack = Acknowledgement(assignment=a, sent_at=sent, expires_at=sent + timedelta(days=7))
        age = (today - when).days
        if age > 7 or rng.random() < 0.55:
            roll = rng.random()
            if age <= 7 or roll < 0.93:
                ack.status = AckStatus.ACCEPTED
                ack.responded_at = _past(sent + timedelta(hours=rng.randint(1, 70)), rng)
                ack.typed_name = emp.full_name
                ack.ip_address = f"10.20.{rng.randint(1, 4)}.{rng.randint(10, 250)}"
                ack.user_agent = rng.choice(["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0",
                                             "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) Safari/18.1",
                                             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/141.0"])
            elif roll < 0.96:
                ack.status = AckStatus.DISPUTED
                ack.responded_at = _past(sent + timedelta(hours=rng.randint(2, 48)), rng)
                ack.comment = rng.choice(["Not received yet, still at reception?", "Serial number does not match the device I got.",
                                          "Received a different charger (65 W instead of 90 W)."])
            else:
                ack.status = AckStatus.EXPIRED
        session.add(ack)
        asset.status = AssetStatus.ASSIGNED
        asset.location = emp.location
        audit(a.checked_out_at, asset, "check_out", f"Checked out to {emp.audit_label()}",
              {"status": [AssetStatus.IN_STOCK, AssetStatus.ASSIGNED]}, employee=emp)
        if ack.responded_at:
            audit(ack.responded_at, a, f"ack_{ack.status.lower()}", f"{emp.full_name} {ack.status.lower()} {asset.asset_tag}", by_employee=True)
        counts["assignments"] += 1
        return a

    def checkin(a: Assignment, when: date, condition: str = "Good") -> None:
        a.checked_in_at = _at(when, rng)
        a.checked_in_by_id = rng.choice(it_staff).id
        a.return_condition = condition
        a.asset.status = AssetStatus.IN_STOCK
        audit(a.checked_in_at, a.asset, "check_in", f"Returned by {a.employee.audit_label()} ({condition})",
              {"status": [AssetStatus.ASSIGNED, AssetStatus.IN_STOCK]}, employee=a.employee)

    def repair(asset: Asset, when: date, *, open_: bool = False) -> Repair:
        rtype = "Warranty" if asset.warranty_end_date and asset.warranty_end_date > when else rng.choice(["Paid", "Internal"])
        r = Repair(asset=asset, reported_at=when, issue=rng.choice(ISSUES), repair_type=rtype,
                   vendor=rng.choice(vendors) if rtype != "Internal" else None,
                   rma_number=f"RMA-{rng.randint(100000, 999999)}" if rtype == "Warranty" else None)
        previous = asset.status
        audit(_at(when, rng), asset, "repair_opened", r.issue, {"status": [previous, AssetStatus.IN_REPAIR]})
        if not open_:
            r.completed_at = when + timedelta(days=rng.randint(3, 21))
            r.outcome = rng.choices(["Fixed", "Replaced"], [85, 15])[0]
            r.resolution = rng.choice(RESOLUTIONS)
            r.cost = Decimal(0) if rtype == "Warranty" else Decimal(rng.choice([45, 89, 129, 189, 240]))
            audit(_at(r.completed_at, rng), asset, "repair_closed", f"Repair closed: {r.outcome}",
                  {"status": [AssetStatus.IN_REPAIR, previous]})
        else:
            asset.status = AssetStatus.IN_REPAIR
        session.add(r)
        counts["repairs"] += 1
        return r

    rng.shuffle(assets)
    n = len(assets)
    plan = (["disposed"] * int(n * 0.04) + ["retired"] * int(n * 0.05) + ["repair"] * int(n * 0.035)
            + ["stock"] * int(n * 0.17))
    plan += ["assigned"] * (n - len(plan))
    for asset, fate in zip(assets, plan):
        start = asset.purchase_date + timedelta(days=rng.randint(2, 20))
        if start >= today:
            start = asset.purchase_date
        age = (today - start).days
        # Older devices often had a previous holder.
        cursor = start
        if age > 500 and rng.random() < 0.55:
            prev = checkout(asset, rng.choice(holder_pool[:len(active_employees)]), cursor)
            cursor = cursor + timedelta(days=rng.randint(120, max(age - 200, 121)))
            checkin(prev, cursor, rng.choice(["Good", "Good", "Fair"]))
            cursor += timedelta(days=rng.randint(2, 30))
        if age > 200 and rng.random() < 0.18 and cursor < today - timedelta(days=60):
            repair(asset, cursor + timedelta(days=rng.randint(5, 40)))

        if fate in ("retired", "disposed"):
            retired_on = min(asset.purchase_date + timedelta(days=asset.life_months * 30 + rng.randint(-120, 200)),
                             today - timedelta(days=rng.randint(3, 60)))
            retired_on = max(retired_on, cursor + timedelta(days=1))
            if retired_on > today:
                retired_on = today
            reason = rng.choices(["End of life", "Damaged beyond repair", "Lost", "Stolen"], [70, 18, 8, 4])[0]
            d = Disposal(asset=asset, retired_at=retired_on, retire_reason=reason)
            asset.status = AssetStatus.RETIRED
            audit(_at(retired_on, rng), asset, "retire", reason, {"status": [AssetStatus.IN_STOCK, AssetStatus.RETIRED]})
            if fate == "disposed" and reason not in ("Lost", "Stolen"):
                d.disposed_at = min(retired_on + timedelta(days=rng.randint(7, 60)), today)
                d.method = rng.choices(["Recycled", "Sold", "Donated", "Destroyed"], [50, 25, 15, 10])[0]
                d.recipient = {"Recycled": "GreenCycle Elektronik GmbH", "Sold": "Staff resale programme",
                               "Donated": "Digitale Schule e.V.", "Destroyed": "SecureShred Nord GmbH"}[d.method]
                d.data_wipe_method = "Physical destruction" if d.method == "Destroyed" else rng.choice(["NIST 800-88 purge", "Cryptographic erase"])
                d.data_wipe_confirmed = True
                d.sale_value = Decimal(rng.randint(60, 320)) if d.method == "Sold" else None
                asset.status = AssetStatus.DISPOSED
                audit(_at(d.disposed_at, rng), asset, "dispose", d.method, {"status": [AssetStatus.RETIRED, AssetStatus.DISPOSED]})
            session.add(d)
            counts["disposals"] += 1
        elif fate == "repair":
            if rng.random() < 0.5:
                checkout(asset, rng.choice(active_employees), cursor)
            repair(asset, today - timedelta(days=rng.randint(1, 12)), open_=True)
        elif fate == "assigned":
            emp = rng.choice(holder_pool)
            recent = rng.random() < 0.08
            when = today - timedelta(days=rng.randint(0, 9)) if recent else max(cursor, today - timedelta(days=rng.randint(15, 700)))
            when = max(when, asset.purchase_date)
            loan = rng.random() < 0.06
            if loan:
                when = today - timedelta(days=rng.randint(10, 50))
                emp = rng.choice(active_employees)
            checkout(asset, emp, when, loan=loan)

    session.flush()
    session.execute(AuditLog.__table__.insert(), audit_rows)
    session.commit()
    session.info.pop("skip_audit", None)
    return {
        "users": len(it_staff),
        "employees": len(employees),
        "assets": len(assets),
        **counts,
        "audit entries": len(audit_rows),
    }
