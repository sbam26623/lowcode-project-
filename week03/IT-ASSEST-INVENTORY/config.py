import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # SQLite for local demo; set DATABASE_URL=postgresql+psycopg://... for PostgreSQL (spec §7.1).
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'inventory.db'}"
    )

    # FR-AUTH-06: 30-minute idle timeout, hardened cookies.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    # Organisation settings (spec §4 "setting"; open question 1 answered: EUR, Germany).
    ORG_NAME = "Nordwind Logistik GmbH"
    CURRENCY = "EUR"
    TIMEZONE = "Europe/Berlin"
    ASSET_TAG_PATTERN = "IT-{:06d}"
    IT_TEAM_EMAIL = "it-assets@nordwind.example"

    ACK_VALID_DAYS = 7
    ACK_REMINDER_DAYS = 3
    WARRANTY_NOTICE_DAYS = (60, 30)
    LOCKOUT_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
