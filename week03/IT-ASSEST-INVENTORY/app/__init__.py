"""Application factory (spec §7.2)."""
from __future__ import annotations

import warnings
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask import Flask, redirect, request, session, url_for
from flask_login import current_user
from sqlalchemy import exc as sa_exc

from config import Config

from .extensions import csrf, db, login_manager

# SQLite stores Numeric as float; harmless for the demo, PostgreSQL keeps exact decimals.
warnings.filterwarnings("ignore", category=sa_exc.SAWarning, message=".*Decimal objects natively.*")

PUBLIC_ENDPOINTS = {"auth.login", "static"}

STATUS_BADGES = {
    "In Stock": "success",
    "Assigned": "primary",
    "In Repair": "warning",
    "Retired": "secondary",
    "Disposed": "dark",
    "Pending": "warning",
    "Accepted": "success",
    "Disputed": "danger",
    "Expired": "secondary",
}


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from . import audit  # noqa: F401  registers the flush listeners
    from .ack.routes import bp as ack_bp
    from .assets.routes import bp as assets_bp
    from .auth.routes import bp as auth_bp
    from .dashboard.routes import bp as dashboard_bp
    from .employees.routes import bp as employees_bp
    from .reports.routes import bp as reports_bp

    for bp in (auth_bp, dashboard_bp, assets_bp, employees_bp, reports_bp, ack_bp):
        app.register_blueprint(bp)

    @app.before_request
    def require_login():
        # Every IT page needs a session; employees only reach the signed /ack links.
        if request.endpoint in PUBLIC_ENDPOINTS or (request.endpoint or "").startswith("ack."):
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.full_path))
        session.permanent = True  # sliding 30-minute idle timeout
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    _register_filters(app)
    _register_cli(app)
    return app


def _register_filters(app: Flask) -> None:
    tz = ZoneInfo(app.config["TIMEZONE"])

    @app.template_filter("eur")
    def eur(value) -> str:
        if value is None:
            return "—"
        # German number format: 1.234,56 €
        text = f"{Decimal(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"{text} €"

    @app.template_filter("d")
    def format_date(value) -> str:
        if value is None:
            return "—"
        if isinstance(value, datetime):
            value = value.replace(tzinfo=timezone.utc).astimezone(tz).date()
        return value.strftime("%d.%m.%Y")

    @app.template_filter("dt")
    def format_datetime(value) -> str:
        if value is None:
            return "—"
        return value.replace(tzinfo=timezone.utc).astimezone(tz).strftime("%d.%m.%Y %H:%M")

    @app.template_filter("badge")
    def badge(status: str) -> str:
        return STATUS_BADGES.get(status, "light")

    app.jinja_env.tests["date"] = lambda value: isinstance(value, date)

    @app.context_processor
    def inject_globals():
        return {"org_name": app.config["ORG_NAME"], "today": date.today()}


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    @click.option("--assets", default=320, show_default=True)
    @click.option("--employees", default=120, show_default=True)
    @click.option("--seed", "rng_seed", default=2026, show_default=True)
    def seed_command(assets: int, employees: int, rng_seed: int) -> None:
        """Drop and recreate the database with random demo data."""
        from .seed import seed

        summary = seed(n_assets=assets, n_employees=employees, rng_seed=rng_seed)
        for key, value in summary.items():
            click.echo(f"{key:>14}: {value}")

    @app.cli.command("daily-job")
    def daily_job_command() -> None:
        """Run the 07:00 notification job once."""
        from .services.notifications import run_daily_job

        with app.test_request_context(base_url=app.config.get("BASE_URL", "http://localhost:5000")):
            for key, value in run_daily_job().items():
                click.echo(f"{key:>14}: {value}")
