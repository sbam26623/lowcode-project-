"""SQLAlchemy models (spec §4). Timestamps are stored as naive UTC."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AssetStatus:
    IN_STOCK = "In Stock"
    ASSIGNED = "Assigned"
    IN_REPAIR = "In Repair"
    RETIRED = "Retired"
    DISPOSED = "Disposed"
    ALL = [IN_STOCK, ASSIGNED, IN_REPAIR, RETIRED, DISPOSED]
    ACTIVE = [IN_STOCK, ASSIGNED, IN_REPAIR]


class AckStatus:
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DISPUTED = "Disputed"
    EXPIRED = "Expired"
    ALL = [PENDING, ACCEPTED, DISPUTED, EXPIRED]


class Role:
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"


CONDITIONS = ["New", "Good", "Fair", "Damaged"]
REPAIR_TYPES = ["Warranty", "Paid", "Internal"]
REPAIR_OUTCOMES = ["Fixed", "Replaced", "Beyond repair"]
RETIRE_REASONS = ["End of life", "Damaged beyond repair", "Lost", "Stolen", "Other"]
DISPOSAL_METHODS = ["Recycled", "Sold", "Donated", "Destroyed", "Returned to lessor"]
WIPE_METHODS = ["NIST 800-88 purge", "Cryptographic erase", "Physical destruction", "Not applicable"]


class Timestamped:
    """Common columns; audited models also get field-level audit_log rows (app/audit.py)."""

    __audited__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(Integer)
    updated_by_id: Mapped[int | None] = mapped_column(Integer)

    def audit_label(self) -> str:
        return f"{type(self).__name__} #{self.id}"


class User(UserMixin, Timestamped, db.Model):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default=Role.MANAGER)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def is_active(self) -> bool:  # Flask-Login hook
        return self.active

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def audit_label(self) -> str:
        return self.email


class Location(Timestamped, db.Model):
    __tablename__ = "location"

    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def audit_label(self) -> str:
        return self.name


class Department(Timestamped, db.Model):
    __tablename__ = "department"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def audit_label(self) -> str:
        return self.name


class Category(Timestamped, db.Model):
    __tablename__ = "category"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    default_useful_life_months: Mapped[int] = mapped_column(Integer, default=36)
    default_residual_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("10"))
    custom_field_schema: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def audit_label(self) -> str:
        return self.name


class Manufacturer(Timestamped, db.Model):
    __tablename__ = "manufacturer"

    name: Mapped[str] = mapped_column(String(120), unique=True)

    def audit_label(self) -> str:
        return self.name


class AssetModel(Timestamped, db.Model):
    __tablename__ = "model"

    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturer.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    name: Mapped[str] = mapped_column(String(120))
    model_number: Mapped[str | None] = mapped_column(String(80))
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer)

    manufacturer: Mapped[Manufacturer] = relationship(lazy="joined")
    category: Mapped[Category] = relationship(lazy="joined")

    @property
    def display_name(self) -> str:
        return f"{self.manufacturer.name} {self.name}"

    def audit_label(self) -> str:
        return self.name


class Vendor(Timestamped, db.Model):
    __tablename__ = "vendor"

    name: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(60))

    def audit_label(self) -> str:
        return self.name


class Employee(Timestamped, db.Model):
    __tablename__ = "employee"

    employee_code: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE / LEAVER
    leaving_date: Mapped[date | None] = mapped_column(Date)

    department: Mapped[Department | None] = relationship(lazy="joined")
    location: Mapped[Location | None] = relationship(lazy="joined")
    manager: Mapped[Employee | None] = relationship(remote_side="Employee.id")

    @property
    def is_leaver(self) -> bool:
        return self.status == "LEAVER"

    def audit_label(self) -> str:
        return f"{self.full_name} ({self.employee_code})"


class Asset(Timestamped, db.Model):
    __tablename__ = "asset"

    asset_tag: Mapped[str] = mapped_column(String(40), unique=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model.id"))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default=AssetStatus.IN_STOCK, index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"), index=True)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"))
    invoice_number: Mapped[str | None] = mapped_column(String(80))
    warranty_end_date: Mapped[date | None] = mapped_column(Date, index=True)
    useful_life_months: Mapped[int | None] = mapped_column(Integer)
    residual_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    custom_fields: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    model: Mapped[AssetModel] = relationship(lazy="joined")
    location: Mapped[Location | None] = relationship(lazy="joined")
    vendor: Mapped[Vendor | None] = relationship()
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="asset", order_by="Assignment.checked_out_at.desc()"
    )
    open_assignment: Mapped[Assignment | None] = relationship(
        primaryjoin="and_(Assignment.asset_id == Asset.id, Assignment.checked_in_at.is_(None))",
        viewonly=True,
        uselist=False,
    )
    repairs: Mapped[list[Repair]] = relationship(
        back_populates="asset", order_by="Repair.reported_at.desc()"
    )
    disposal: Mapped[Disposal | None] = relationship(back_populates="asset", uselist=False)

    @property
    def life_months(self) -> int:
        return self.useful_life_months or self.model.category.default_useful_life_months

    @property
    def residual(self) -> Decimal:
        return self.residual_pct if self.residual_pct is not None else self.model.category.default_residual_pct

    def audit_label(self) -> str:
        return self.asset_tag


class Assignment(Timestamped, db.Model):
    __tablename__ = "assignment"
    __table_args__ = (
        # Spec §4: at most one open assignment per asset.
        Index(
            "uq_assignment_open_per_asset",
            "asset_id",
            unique=True,
            sqlite_where=text("checked_in_at IS NULL"),
            postgresql_where=text("checked_in_at IS NULL"),
        ),
    )

    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    checked_out_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    checked_out_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    expected_return_date: Mapped[date | None] = mapped_column(Date)
    checkout_condition: Mapped[str | None] = mapped_column(String(20))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    checked_in_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    return_condition: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    asset: Mapped[Asset] = relationship(back_populates="assignments")
    employee: Mapped[Employee] = relationship(lazy="joined")
    acknowledgement: Mapped[Acknowledgement | None] = relationship(
        back_populates="assignment", uselist=False, lazy="joined"
    )

    @property
    def is_open(self) -> bool:
        return self.checked_in_at is None

    def is_overdue(self, today: date) -> bool:
        if not self.is_open:
            return False
        if self.expected_return_date and self.expected_return_date < today:
            return True
        emp = self.employee
        return bool(emp.is_leaver and emp.leaving_date and emp.leaving_date < today)


class Acknowledgement(Timestamped, db.Model):
    __tablename__ = "acknowledgement"

    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignment.id"), unique=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default=AckStatus.PENDING)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)
    typed_name: Mapped[str | None] = mapped_column(String(200))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    comment: Mapped[str | None] = mapped_column(Text)

    assignment: Mapped[Assignment] = relationship(back_populates="acknowledgement")

    @property
    def effective_status(self) -> str:
        """Pending links past expiry count as Expired even before the daily job runs."""
        if self.status == AckStatus.PENDING and self.expires_at < utcnow():
            return AckStatus.EXPIRED
        return self.status


class Repair(Timestamped, db.Model):
    __tablename__ = "repair"

    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"))
    reported_at: Mapped[date] = mapped_column(Date)
    issue: Mapped[str] = mapped_column(Text)
    repair_type: Mapped[str] = mapped_column(String(20))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"))
    rma_number: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[date | None] = mapped_column(Date)
    resolution: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    outcome: Mapped[str | None] = mapped_column(String(20))

    asset: Mapped[Asset] = relationship(back_populates="repairs")
    vendor: Mapped[Vendor | None] = relationship()

    @property
    def is_open(self) -> bool:
        return self.completed_at is None


class Disposal(Timestamped, db.Model):
    __tablename__ = "disposal"

    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), unique=True)
    retired_at: Mapped[date] = mapped_column(Date)
    retire_reason: Mapped[str] = mapped_column(String(40))
    retire_notes: Mapped[str | None] = mapped_column(Text)
    disposed_at: Mapped[date | None] = mapped_column(Date)
    method: Mapped[str | None] = mapped_column(String(40))
    recipient: Mapped[str | None] = mapped_column(String(200))
    data_wipe_method: Mapped[str | None] = mapped_column(String(60))
    data_wipe_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sale_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    asset: Mapped[Asset] = relationship(back_populates="disposal")


class EmailLog(db.Model):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_address: Mapped[str] = mapped_column(String(255))
    template_code: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="LOGGED")
    error: Mapped[str | None] = mapped_column(Text)


class AuditLog(db.Model):
    """Append-only (FR-AUD-03). asset_id / employee_id link entries to detail-page timelines."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    entity_label: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(40))
    changes: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(String(400))
    asset_id: Mapped[int | None] = mapped_column(Integer, index=True)
    employee_id: Mapped[int | None] = mapped_column(Integer, index=True)

    user: Mapped[User | None] = relationship()


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _audit_is_append_only(mapper, connection, target):
    raise PermissionError("audit_log entries cannot be modified or deleted")

