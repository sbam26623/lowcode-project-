# IT Asset Inventory

Flask implementation of [IT_Asset_Inventory_Spec.md](IT_Asset_Inventory_Spec.md), seeded with random demo data for a fictional German company (Nordwind Logistik GmbH, four sites, EUR).

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m flask --app app:create_app seed   # drops and recreates instance/inventory.db
.venv/Scripts/python run.py                               # http://localhost:5000
```

Demo sign-ins are in the docstring of [app/seed.py](app/seed.py). `flask --app app:create_app daily-job` runs the 07:00 notification job once. Run the tests with `.venv/Scripts/python -m pytest`.

SQLite is used locally because Docker/PostgreSQL were not available. Set `DATABASE_URL=postgresql+psycopg://...` (and install `psycopg`) to use PostgreSQL as the spec requires.

## Prototype

[prototype/index.html](prototype/index.html) is a standalone, clickable version of the same data with the lifecycle rules running in the browser. Rebuild it after reseeding with `python prototype/build.py`.

## Decisions taken for open questions (spec §12)

| # | Question | Used in this build |
|---|---|---|
| 1 | Currency, useful lives | EUR; laptops/desktops/docks/peripherals 36 months, monitors 60, phones/tablets 24; 10 % residual |
| 2 | Acceptable-use text | Placeholder text in `app/ack/routes.py` |
| 3 | Email service | None yet: emails are written to `email_log` and the acknowledgement link is shown on screen |
| 4 | Hosting | Not decided; runs locally |

## What is in this slice

- Dashboard (§3.11), asset list/detail/create (§3.4), lifecycle rules (§3.5), check-out/check-in with the public e-acknowledgement page (§3.6), repairs (§3.7), straight-line depreciation (§3.8), employees and leaver checklist (§3.3), reports RPT-01/02/03/04/05/08 with CSV export, and the append-only audit log with field-level diffs (§3.12).
- Login with Argon2 hashing, 12-character minimum, 5-attempt lockout and a 30-minute idle timeout.

Not built yet: TOTP MFA and password reset (FR-AUTH-03/05), user and reference-data admin screens, CSV/XLSX import (§3.9), XLSX export, maintenance plans, attachments, editable email templates, Alembic migrations, Docker.
