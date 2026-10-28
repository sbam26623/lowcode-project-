"""Login / logout with lockout (FR-AUTH-01, -02, -04). TOTP MFA (FR-AUTH-03) is not in this demo."""
from __future__ import annotations

from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func, select

from ..audit import log_event
from ..extensions import db, login_manager
from ..models import User, utcnow

bp = Blueprint("auth", __name__)
hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Passwords must be at least 12 characters.")
    return hasher.hash(password)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))


def _safe_next(target: str | None) -> str:
    if target and not urlsplit(target).netloc and target.startswith("/"):
        return target
    return url_for("dashboard.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.scalar(select(User).where(func.lower(User.email) == email))
        now = utcnow()
        if user and user.locked_until and user.locked_until > now:
            log_event("login_locked", entity_type="user", entity_id=user.id, label=email, user_id=user.id)
            db.session.commit()
            flash("This account is temporarily locked. Try again later.", "danger")
            return render_template("auth/login.html", email=email), 429
        try:
            ok = bool(user and user.active and hasher.verify(user.password_hash, password))
        except (VerifyMismatchError, InvalidHashError):
            ok = False
        if not ok:
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= current_app.config["LOCKOUT_ATTEMPTS"]:
                    user.locked_until = now + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
                    user.failed_login_count = 0
            log_event("login_failed", entity_type="user", entity_id=user.id if user else None, label=email,
                      user_id=user.id if user else None)
            db.session.commit()
            flash("Email or password is incorrect.", "danger")
            return render_template("auth/login.html", email=email), 401
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        login_user(user)
        log_event("login", entity_type="user", entity_id=user.id, label=user.email)
        db.session.commit()
        return redirect(_safe_next(request.args.get("next")))
    return render_template("auth/login.html", email="")


@bp.route("/logout", methods=["POST"])
def logout():
    log_event("logout", entity_type="user", entity_id=current_user.id, label=current_user.email)
    db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
