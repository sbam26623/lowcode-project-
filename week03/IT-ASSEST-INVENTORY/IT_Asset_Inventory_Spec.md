# IT Asset Inventory Web Application — Software Requirements Specification

**Version:** 1.0 (Draft)
**Date:** 28 October 2026
**Status:** For review

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for a web-based IT Asset Inventory application. The system lets the IT team record, assign, maintain and retire end-user hardware across several office locations, with a full audit trail, employee e-acknowledgement of assigned equipment, depreciation tracking and operational reporting.

### 1.2 Scope

In scope:

- End-user hardware: laptops, desktops, monitors, docking stations, phones, tablets and peripherals.
- Asset lifecycle: In Stock, Assigned, In Repair / Maintenance, Retired, Disposed.
- Check-out / check-in to employees with email-based e-acknowledgement.
- Repair log and scheduled (recurring) maintenance.
- Purchase information and straight-line depreciation.
- Email notifications, dashboards and reports.
- Full audit trail of every change.

Out of scope (for this release):

- Infrastructure assets (servers, network, storage), software licences and cloud resources.
- Procurement / purchase-order workflow.
- Barcode, QR or RFID scanning (asset tag numbers are entered manually).
- Automated discovery (agents, network scanning, MDM sync).
- SSO / directory integration.
- Native mobile apps or mobile-optimised layouts.
- Migration of legacy data (the system starts fresh).

### 1.3 Requirements Summary (from discovery questionnaire)

| # | Topic | Decision |
|---|---|---|
| 1 | Scale | Under 1,000 assets |
| 2 | Asset types | End-user hardware only |
| 3 | User roles | Admin, IT Asset Manager |
| 4 | Hosting | Undecided — recommendation in section 9 |
| 5 | Lifecycle stages | In Stock / Assigned, Repair / Maintenance, Retired / Disposed |
| 6 | Identification | Asset tag number only (no scanning) |
| 7 | Data entry | Manual entry + CSV/Excel import |
| 8 | Assignment | Check-out / check-in with employee e-acknowledgement |
| 9 | Authentication | Local accounts (with MFA) |
| 10 | Notifications | Warranty expiry, assignment acknowledgement, overdue returns, low stock |
| 11 | Finance | Purchase information + depreciation |
| 12 | Locations | Multiple sites, one country |
| 13 | Reports | Inventory by status/location, assets by employee, warranty & aging, financial/depreciation |
| 14 | Audit | Full audit trail (who / when / old value / new value) |
| 15 | Device access | Desktop browsers only |
| 16 | Maintenance | Repair log + scheduled maintenance |
| 17 | Tech stack | Python (Flask) |
| 18 | Database | PostgreSQL |
| 19 | Data migration | None — starting fresh |
| 20 | Timeline | MVP in about 2 months |

### 1.4 Definitions

| Term | Meaning |
|---|---|
| Asset | A single physical hardware item identified by a unique asset tag. |
| Asset Tag | Unique, human-readable identifier (e.g. `IT-000123`) affixed to the device. |
| Model | A make/model combination (e.g. "Dell Latitude 7450") shared by many assets. |
| Category | Asset type grouping (Laptop, Monitor, Phone, etc.). |
| Employee | A person who can hold assets. Employees are records, not system users. |
| Check-out | Assigning an asset to an employee. |
| Check-in | Returning an asset from an employee to stock. |
| e-Acknowledgement | Employee confirmation of receipt via a secure, single-use email link. |
| Book Value | Purchase cost minus accumulated depreciation. |

## 2. Users and Roles

Only IT staff log in to the application. Employees interact only through acknowledgement emails and a public acknowledgement page reached by a signed link.

| Capability | Admin | IT Asset Manager |
|---|---|---|
| View assets, employees, reports, dashboard | Yes | Yes |
| Create / edit / check-out / check-in assets | Yes | Yes |
| Log repairs and complete maintenance tasks | Yes | Yes |
| Import assets and employees from CSV/Excel | Yes | Yes |
| Retire / dispose assets | Yes | Yes |
| Delete records (soft delete) | Yes | No |
| Manage users and roles | Yes | No |
| Manage reference data (categories, models, locations, vendors, depreciation rules) | Yes | No |
| Configure notification settings and SMTP | Yes | No |
| View full audit log | Yes | Yes (read-only) |

## 3. Functional Requirements

Requirement priorities: **M** = Must (MVP), **S** = Should (MVP if time allows), **C** = Could (Phase 2).

### 3.1 Authentication and User Management

| ID | Requirement | Priority |
|---|---|---|
| FR-AUTH-01 | Users sign in with email and password (local accounts). | M |
| FR-AUTH-02 | Passwords hashed with Argon2id (or bcrypt); minimum 12 characters; checked against a common-password list. | M |
| FR-AUTH-03 | Time-based one-time password (TOTP) MFA, mandatory for Admins and optional-but-encouraged for Managers. | M |
| FR-AUTH-04 | Account lockout after 5 failed attempts for 15 minutes; all attempts logged. | M |
| FR-AUTH-05 | Self-service password reset via time-limited email link (valid 30 minutes, single use). | M |
| FR-AUTH-06 | Sessions expire after 30 minutes of inactivity; secure, HttpOnly, SameSite cookies. | M |
| FR-AUTH-07 | Admin can create, deactivate and reactivate users and change their role. Users are never hard-deleted. | M |

### 3.2 Reference Data (Admin)

| ID | Requirement | Priority |
|---|---|---|
| FR-REF-01 | Manage **Locations** (site name, address, optional sub-location such as floor/room). | M |
| FR-REF-02 | Manage **Categories** (Laptop, Desktop, Monitor, Phone, Tablet, Docking Station, Peripheral, Other) with default useful life for depreciation. | M |
| FR-REF-03 | Manage **Manufacturers** and **Models** (model belongs to a manufacturer and a category; optional low-stock threshold per model). | M |
| FR-REF-04 | Manage **Vendors / Suppliers** (name, contact, phone, email). | M |
| FR-REF-05 | Manage **Departments** for employees. | M |
| FR-REF-06 | Reference records in use cannot be deleted, only deactivated. | M |

### 3.3 Employees

| ID | Requirement | Priority |
|---|---|---|
| FR-EMP-01 | Create and edit employees: employee ID, full name, email, department, location, manager, status (Active / Leaver), leaving date. | M |
| FR-EMP-02 | Bulk import employees from CSV/XLSX (see 3.9). | M |
| FR-EMP-03 | Employee detail page shows current assets, full assignment history and acknowledgement status. | M |
| FR-EMP-04 | Marking an employee as Leaver with a leaving date flags all their assets as "Return due" on that date. | M |
| FR-EMP-05 | Printable "Leaver return checklist" listing all assets held by the employee. | S |

### 3.4 Asset Management

| ID | Requirement | Priority |
|---|---|---|
| FR-AST-01 | Create an asset with: asset tag (unique, required), model, serial number (unique per manufacturer), status, location, purchase date, purchase cost, vendor, invoice/PO number, warranty end date, notes. | M |
| FR-AST-02 | Asset tag can be auto-generated from a configurable pattern (e.g. `IT-{000000}`) or entered manually. | M |
| FR-AST-03 | Optional category-specific fields: e.g. Laptop — CPU, RAM, storage, OS; Phone — IMEI, phone number. Implemented as configurable custom fields per category. | S |
| FR-AST-04 | Attach files to an asset (invoice PDF, photos, disposal certificate); max 10 MB per file. | S |
| FR-AST-05 | Asset list with server-side pagination, sorting, free-text search (tag, serial, model, assignee) and filters (status, category, location, model, assignee, warranty status). | M |
| FR-AST-06 | Export the current filtered asset list to CSV and XLSX. | M |
| FR-AST-07 | Asset detail page shows all fields, current assignee, depreciation/book value, repair log, maintenance schedule, attachments and a timeline of all history. | M |
| FR-AST-08 | Bulk actions on selected assets: change location, change status, export. | S |
| FR-AST-09 | Clone an asset to quickly create similar items (serial and tag cleared). | S |

### 3.5 Asset Lifecycle

Statuses and permitted transitions:

| From | To | Trigger |
|---|---|---|
| In Stock | Assigned | Check-out to employee |
| Assigned | In Stock | Check-in |
| In Stock / Assigned | In Repair | Repair opened |
| In Repair | In Stock / Assigned | Repair closed (returns to previous holder if still assigned) |
| In Stock / In Repair | Retired | Retire action (reason required) |
| Retired | Disposed | Dispose action (method, date, data-wipe confirmation) |
| Retired | In Stock | Reinstate (Admin only) |

| ID | Requirement | Priority |
|---|---|---|
| FR-LC-01 | System enforces the transition table above; invalid transitions are rejected with a clear message. | M |
| FR-LC-02 | An asset must be checked in before it can be retired. | M |
| FR-LC-03 | Retirement captures reason (End of life, Damaged beyond repair, Lost, Stolen, Other) and date. | M |
| FR-LC-04 | Disposal captures method (Recycled, Sold, Donated, Destroyed, Returned to lessor), date, recipient/vendor, data-wipe method and confirmation, sale value (if any) and certificate attachment. | M |
| FR-LC-05 | Disposed assets are read-only and hidden from default lists (visible via filter). | M |

### 3.6 Check-out, Check-in and e-Acknowledgement

| ID | Requirement | Priority |
|---|---|---|
| FR-ASN-01 | Check-out an In Stock asset to an active employee, recording checkout date, expected return date (optional, for loans), condition and notes. | M |
| FR-ASN-02 | On check-out the system emails the employee a secure acknowledgement link (signed, single-use token, valid 7 days). | M |
| FR-ASN-03 | The acknowledgement page (no login) shows asset details and the IT acceptable-use terms; the employee types their full name and clicks **Accept**. The system records name typed, timestamp, IP address and user agent. | M |
| FR-ASN-04 | The employee can instead click **Report a problem** (e.g. "not received", "wrong item") with a comment; IT is notified. | S |
| FR-ASN-05 | Acknowledgement status per assignment: Pending, Accepted, Disputed, Expired. Managers can resend the link. | M |
| FR-ASN-06 | Reminder email sent if pending after 3 days; status set to Expired after 7 days and IT notified. | M |
| FR-ASN-07 | Check-in records return date, condition on return and notes, and sets status back to In Stock (or In Repair if condition = Damaged). | M |
| FR-ASN-08 | Bulk check-out of multiple assets to one employee (single acknowledgement email listing all items). | S |
| FR-ASN-09 | Printable assignment receipt (PDF) for each assignment. | C |

### 3.7 Repairs and Scheduled Maintenance

| ID | Requirement | Priority |
|---|---|---|
| FR-MNT-01 | Open a repair record: reported date, issue description, repair type (Warranty / Paid / Internal), vendor, ticket/RMA number. Asset moves to In Repair. | M |
| FR-MNT-02 | Close a repair: completed date, resolution, cost, outcome (Fixed / Replaced / Beyond repair). "Beyond repair" prompts retirement. | M |
| FR-MNT-03 | Repair costs roll up into asset total cost of ownership and reports. | S |
| FR-MNT-04 | Define maintenance plans per asset or per model: task name, interval (days/months), next due date, instructions. | M |
| FR-MNT-05 | "Maintenance due" list showing overdue and upcoming (next 30 days) tasks; marking a task complete records who/when/notes and schedules the next occurrence. | M |
| FR-MNT-06 | Email digest of maintenance tasks due within 7 days. | S |

### 3.8 Financials and Depreciation

| ID | Requirement | Priority |
|---|---|---|
| FR-FIN-01 | Record purchase cost, currency (single currency, configured at setup), purchase date, vendor, invoice number. | M |
| FR-FIN-02 | Straight-line depreciation: monthly depreciation = (cost − residual value) ÷ useful life in months. Useful life and residual % default from category, overridable per asset. | M |
| FR-FIN-03 | Book value calculated on the fly as at today or any chosen date; never below residual value. | M |
| FR-FIN-04 | Depreciation stops at disposal; disposal gain/loss = sale value − book value at disposal date. | S |
| FR-FIN-05 | Financial report by category/location: total cost, accumulated depreciation, book value, purchases in period. | M |

### 3.9 Data Import and Export

| ID | Requirement | Priority |
|---|---|---|
| FR-IMP-01 | Import assets and employees from CSV or XLSX using downloadable templates. | M |
| FR-IMP-02 | Import wizard: upload → column mapping → validation preview (row-level errors shown) → confirm. | M |
| FR-IMP-03 | Validation: required fields, unique asset tag/serial, valid dates and numbers, reference data must exist (or option to auto-create models/locations). | M |
| FR-IMP-04 | Import is all-or-nothing per file; import job history kept with counts and error file download. | M |
| FR-IMP-05 | Limits: up to 5,000 rows / 10 MB per file. | M |

### 3.10 Notifications

All notifications are sent by email via SMTP. A daily scheduled job (07:00 local time) evaluates time-based rules. Admin can enable/disable each rule and set recipients and thresholds.

| ID | Notification | Trigger | Recipients | Priority |
|---|---|---|---|---|
| FR-NOT-01 | Assignment acknowledgement | Asset checked out | Employee | M |
| FR-NOT-02 | Acknowledgement reminder / expired | Pending 3 days / 7 days | Employee / IT team | M |
| FR-NOT-03 | Warranty expiring | 60 and 30 days before warranty end (configurable) | IT team (daily digest) | M |
| FR-NOT-04 | Overdue return | Expected return date passed, or employee leaving date passed with assets outstanding | IT team; employee and their manager | M |
| FR-NOT-05 | Low stock | In Stock count for a model falls below its threshold | IT team | M |
| FR-NOT-06 | Maintenance due | Task due within 7 days or overdue | IT team (digest) | S |
| FR-NOT-07 | Acknowledgement disputed | Employee reports a problem | IT team | S |

Additional notification requirements:

- Email templates editable by Admin with placeholders (e.g. `{employee_name}`, `{asset_tag}`).
- All sent emails logged (recipient, template, time, status) with retry on failure (3 attempts).
- In-app notification bell showing the same alerts for logged-in users. (Priority S)

### 3.11 Dashboard and Reports

Dashboard (home page) widgets:

- Total assets by status (cards).
- Assets by location and by category (bar charts).
- Warranties expiring in next 30/60/90 days.
- Pending acknowledgements and overdue returns.
- Low-stock models.
- Maintenance due this week.
- Total book value.

Reports (all filterable, exportable to CSV/XLSX and printable/PDF):

| ID | Report | Description | Priority |
|---|---|---|---|
| RPT-01 | Inventory by status / location / category | Counts and detailed lists | M |
| RPT-02 | Assets by employee | Current holdings per employee and department; leavers with outstanding assets | M |
| RPT-03 | Warranty status | Expired, expiring within N days, no warranty | M |
| RPT-04 | Asset aging / refresh planning | Age bands (0–1, 1–2, 2–3, 3–4, 4+ years) per category; assets past useful life | M |
| RPT-05 | Depreciation / financial | Cost, accumulated depreciation, book value as at a date; purchases by period | M |
| RPT-06 | Repair and maintenance | Repairs by asset/model/vendor, costs, frequency; maintenance compliance | S |
| RPT-07 | Acknowledgement status | Pending, disputed, expired acknowledgements | S |
| RPT-08 | Disposal register | Retired/disposed assets with method, date, data-wipe confirmation | M |

### 3.12 Audit Trail

| ID | Requirement | Priority |
|---|---|---|
| FR-AUD-01 | Every create, update, delete, status transition, assignment, import, login, logout, failed login and settings change is logged. | M |
| FR-AUD-02 | Each audit entry stores: timestamp (UTC), user, IP address, entity type, entity ID, action, and field-level old and new values (JSON). | M |
| FR-AUD-03 | Audit log is append-only: no UI or API to edit or delete entries; database role used by the app has INSERT/SELECT only on the audit table. | M |
| FR-AUD-04 | Audit log viewer with filters (date range, user, entity, action) and export. | M |
| FR-AUD-05 | Each asset and employee detail page shows its own history timeline from the audit log. | M |
| FR-AUD-06 | Audit records retained for at least 7 years. | M |

## 4. Data Model

Core entities (PostgreSQL). All tables have `id` (primary key), `created_at`, `updated_at`, `created_by`, `updated_by`; business tables use soft delete (`is_active` / `deleted_at`).

| Entity | Key fields |
|---|---|
| **user** | email (unique), password_hash, full_name, role (ADMIN / MANAGER), mfa_secret, mfa_enabled, is_active, last_login_at, failed_login_count, locked_until |
| **location** | name, address, city, parent_id (sub-locations), is_active |
| **department** | name, is_active |
| **category** | name, default_useful_life_months, default_residual_pct, custom_field_schema (JSON) |
| **manufacturer** | name |
| **model** | manufacturer_id, category_id, name, model_number, low_stock_threshold |
| **vendor** | name, contact_name, email, phone |
| **employee** | employee_code (unique), full_name, email, department_id, location_id, manager_id, status (ACTIVE / LEAVER), leaving_date |
| **asset** | asset_tag (unique), model_id, serial_number, status, location_id, current_assignment_id, purchase_date, purchase_cost, vendor_id, invoice_number, warranty_end_date, useful_life_months, residual_pct, custom_fields (JSONB), notes |
| **assignment** | asset_id, employee_id, checked_out_at, checked_out_by, expected_return_date, checkout_condition, checked_in_at, checked_in_by, return_condition, notes |
| **acknowledgement** | assignment_id, token_hash, sent_at, expires_at, status (PENDING / ACCEPTED / DISPUTED / EXPIRED), responded_at, typed_name, ip_address, user_agent, comment |
| **repair** | asset_id, reported_at, issue, repair_type, vendor_id, rma_number, completed_at, resolution, cost, outcome |
| **maintenance_plan** | asset_id or model_id, task_name, interval_value, interval_unit, next_due_date, instructions, is_active |
| **maintenance_log** | plan_id, asset_id, completed_at, completed_by, notes |
| **disposal** | asset_id, retired_at, retire_reason, disposed_at, method, recipient, data_wipe_method, data_wipe_confirmed, sale_value |
| **attachment** | entity_type, entity_id, filename, content_type, size, storage_path |
| **import_job** | type, filename, status, total_rows, success_rows, error_rows, error_file_path |
| **notification_rule** | code, enabled, threshold_days, recipients |
| **email_log** | to, template_code, subject, sent_at, status, error |
| **audit_log** | occurred_at, user_id, ip_address, entity_type, entity_id, action, changes (JSONB) |
| **setting** | key, value (SMTP, asset tag pattern, currency, organisation name) |

Key constraints and indexes:

- Unique: `asset.asset_tag`, (`model.manufacturer_id`, `asset.serial_number`), `employee.employee_code`, `user.email`.
- Partial unique index ensuring only one open assignment (`checked_in_at IS NULL`) per asset.
- Indexes on `asset.status`, `asset.location_id`, `asset.warranty_end_date`, `assignment.employee_id`, `audit_log (entity_type, entity_id)`, `audit_log.occurred_at`.

## 5. User Interface

### 5.1 General

- Desktop browsers only (latest Chrome, Edge, Firefox); minimum width 1280 px. No mobile layout required.
- Server-rendered pages (Flask + Jinja2) with Bootstrap 5 and HTMX for partial updates; Chart.js for dashboard charts.
- Left navigation: Dashboard, Assets, Employees, Assignments, Maintenance, Reports, Import, Audit Log, Admin (Admin only).
- Consistent list pattern: search box, filter panel, sortable columns, pagination (25/50/100), export button.
- Confirmation dialogs for all status changes; inline validation messages.
- Accessibility target: WCAG 2.1 AA for keyboard navigation, contrast and labels.

### 5.2 Key Screens

| Screen | Contents |
|---|---|
| Login / MFA | Email, password, TOTP code; forgot-password link |
| Dashboard | Widgets listed in 3.11 |
| Asset list | Filters, search, bulk actions, export |
| Asset detail | Summary header (tag, model, status badge, assignee), tabs: Details, Assignments, Repairs, Maintenance, Financials, Attachments, History |
| Asset form | Create/edit with category-specific fields |
| Check-out dialog | Employee search, dates, condition, notes |
| Check-in dialog | Return condition, notes |
| Employee list / detail | Current assets, history, acknowledgement status, leaver checklist |
| Maintenance due | Overdue / upcoming tasks with "complete" action |
| Reports | Report picker, parameters, results table, export |
| Import wizard | Upload, mapping, validation preview, confirm |
| Audit log | Filterable log with change diff view |
| Admin | Users, reference data, notification rules, email templates, settings |
| Public acknowledgement page | Asset list, terms, typed-name accept, report problem |

## 6. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | List and detail pages load in under 2 seconds at the 95th percentile with 1,000 assets and 10 concurrent users; reports under 5 seconds. |
| NFR-02 | Capacity | Designed for up to 5,000 assets, 2,000 employees and 25 concurrent users without re-architecture. |
| NFR-03 | Availability | 99.5% during business hours (Mon–Sat 08:00–20:00); planned maintenance outside hours. |
| NFR-04 | Backup | Automated daily full database backup with 30-day retention, plus point-in-time recovery if using a managed database; attachments backed up daily. RPO 24 h, RTO 4 h. Restore tested quarterly. |
| NFR-05 | Security | HTTPS only (TLS 1.2+), HSTS; CSRF protection on all forms; parameterised queries via ORM; output escaping; security headers (CSP, X-Frame-Options); rate-limited login and acknowledgement endpoints. |
| NFR-06 | Security | Role-based access enforced server-side on every route; OWASP Top 10 addressed; dependency vulnerability scanning in CI. |
| NFR-07 | Privacy | Employee personal data limited to name, email, employee ID, department, location. Data handling aligned with the data protection law that applies to the organisation (e.g. GDPR, India DPDP Act 2023). |
| NFR-08 | Usability | A new IT Asset Manager can check out an asset within 5 minutes of first login without training. |
| NFR-09 | Maintainability | Code follows PEP 8; type hints; minimum 70% unit-test coverage on service layer; database changes via migrations only. |
| NFR-10 | Logging & monitoring | Structured application logs; error tracking (e.g. Sentry); uptime check; alerts on failed scheduled jobs and email failures. |
| NFR-11 | Time zone | Store all timestamps in UTC; display in the organisation's configured time zone (set at installation). |

## 7. Technical Architecture

### 7.1 Technology Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | Flask 3.x with Blueprints (application factory pattern) |
| ORM / migrations | SQLAlchemy 2.x + Flask-Migrate (Alembic) |
| Database | PostgreSQL 16 |
| Templates / UI | Jinja2, Bootstrap 5, HTMX, Chart.js |
| Forms & validation | Flask-WTF / WTForms (CSRF built in) |
| Authentication | Flask-Login, argon2-cffi, pyotp (TOTP), itsdangerous (signed tokens) |
| Background & scheduled jobs | Celery + Redis (email sending, imports, daily notification job via Celery Beat). Lighter alternative for MVP: APScheduler in a separate worker process. |
| Import / export | pandas + openpyxl |
| PDF output | WeasyPrint |
| Email | SMTP (e.g. Microsoft 365, Google Workspace, Amazon SES) via Flask-Mail |
| App server | Gunicorn behind Nginx |
| Packaging | Docker + Docker Compose |
| Testing | pytest, pytest-flask, factory-boy, Playwright for end-to-end smoke tests |
| CI/CD | GitHub Actions (lint with ruff, tests, build image, deploy) |

### 7.2 Application Structure

```
app/
  __init__.py          # application factory
  auth/                # login, MFA, password reset
  assets/              # asset CRUD, lifecycle, attachments
  employees/
  assignments/         # check-out/in, acknowledgement
  maintenance/         # repairs, plans, logs
  reports/
  imports/
  admin/               # users, reference data, settings
  audit/               # audit listener + viewer
  services/            # business logic (depreciation, lifecycle rules)
  tasks/               # scheduled and background jobs
  templates/
  static/
migrations/
tests/
```

### 7.3 Audit Implementation

SQLAlchemy `before_flush` / `after_flush` event listeners capture field-level changes on all audited models and write them to `audit_log` in the same transaction, so a change and its audit record are always committed together.

## 8. Integrations

- **SMTP email** — the only external integration in the MVP.
- No SSO, MDM, ticketing or ERP integration in this release. The service layer should be designed so an internal REST API can be added in Phase 2 for future integrations.

## 9. Hosting Recommendation

Hosting was left undecided. Given fewer than 1,000 assets, around 10 concurrent users and a 2-month MVP target, the recommendation is:

**Recommended: a single small cloud virtual machine running Docker Compose, with a managed PostgreSQL database.**

| Component | Suggested sizing |
|---|---|
| App VM (Nginx, Gunicorn/Flask, worker, Redis) | 2 vCPU, 4 GB RAM, 50 GB disk (e.g. Azure B2s, AWS t3.medium, or equivalent in your nearest region) |
| Database | Managed PostgreSQL (Azure Database for PostgreSQL Flexible Server / Amazon RDS), smallest burstable tier, automated backups |
| File storage | Object storage (Azure Blob / Amazon S3) for attachments |
| TLS | Let's Encrypt or cloud-managed certificate |

Rationale: low cost, minimal operations effort, managed backups for the database, and simple to move on-premises later because everything is containerised. If company policy requires on-premises hosting, the same Docker Compose stack runs on a single internal Linux server with a local PostgreSQL instance and scheduled backups to a separate storage location.

Environments: **Development** (local Docker), **Staging** (small VM, test data), **Production**.

## 10. Delivery Plan

### 10.1 MVP (about 8 weeks)

| Week | Deliverables |
|---|---|
| 1 | Project setup, CI/CD, Docker, database schema & migrations, auth (login, MFA, password reset), user management |
| 2 | Reference data admin, employees CRUD, audit logging framework |
| 3 | Asset CRUD, list/search/filters, asset detail, attachments |
| 4 | Lifecycle transitions, check-out/check-in, e-acknowledgement emails and public page |
| 5 | Repairs, maintenance plans and due list; retirement and disposal |
| 6 | Depreciation, CSV/XLSX import wizard, exports |
| 7 | Notifications (daily jobs, templates, email log), dashboard, core reports (RPT-01 to RPT-05, RPT-08) |
| 8 | UAT, bug fixing, security review, production deployment, admin user guide |

MVP includes all requirements marked **M**. Items marked **S** are delivered if capacity allows, otherwise moved to Phase 2.

### 10.2 Phase 2 (candidates)

- Remaining **S** and **C** items (custom fields per category, bulk check-out, PDF receipts, in-app notifications, RPT-06/07).
- QR code label generation and browser-based scanning.
- Microsoft Entra ID / Google SSO.
- Intune / MDM device sync.
- Physical audit (stock-take) campaigns.
- Software licence tracking.
- REST API and integration with a ticketing system.
- Responsive / mobile layout.

## 11. Acceptance Criteria (MVP)

1. An Admin can create users; users must log in with password and (for Admins) TOTP.
2. A Manager can create an asset, check it out to an employee, and the employee receives an acknowledgement email; accepting it records name, time and IP and updates the status to Accepted.
3. Invalid lifecycle transitions are blocked; an assigned asset cannot be retired without check-in.
4. Importing a 500-row asset spreadsheet with one invalid row shows the error and imports nothing until fixed; a clean file imports all rows.
5. Book value on the asset page matches a manual straight-line calculation.
6. Daily job sends warranty-expiry, overdue-return and low-stock emails according to configured thresholds.
7. Every change to an asset appears in its History tab with old and new values; audit entries cannot be modified through the application.
8. All MVP reports can be filtered and exported to CSV and XLSX.
9. Database backup and restore has been tested successfully in staging.

## 12. Assumptions and Open Questions

Assumptions:

- A single organisation (no multi-tenancy) operating in one country with one currency (configured at setup).
- An SMTP account for outbound email will be provided.
- Employee data will be maintained manually or by CSV import (no HR system sync).
- Asset tag labels are printed and attached outside the system.

Open questions:

1. Confirm currency and default useful life per category (suggested: laptops/desktops 36 months, monitors 60 months, phones/tablets 24 months).
2. Confirm the acceptable-use text to display on the acknowledgement page.
3. Which email service (Microsoft 365, Google Workspace, SES) will send notifications?
4. Confirm cloud provider preference or on-premises policy so the hosting recommendation can be finalised.
5. Who will perform User Acceptance Testing, and in which week?
