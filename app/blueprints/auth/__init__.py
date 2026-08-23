import re

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db
from app.models import User, UserStatus, UserRole, VALID_THEMES
from app.blueprints.auth.forms import RegistrationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm

bp = Blueprint("auth", __name__, template_folder="../../templates/auth")

RESET_TOKEN_MAX_AGE = 60 * 60  # 1 hour
RESET_TOKEN_SALT = "password-reset"


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _slugify_username(name, email):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or email.split("@")[0].lower()
    base = base[:40] or "member"
    candidate = base
    n = 1
    while User.query.filter_by(username=candidate).first() is not None:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if existing:
            flash("An account with that email already exists.", "warning")
            return render_template("auth/register.html", form=form)

        name = form.name.data.strip()
        email = form.email.data.lower().strip()

        # Users sign up and can log in immediately — no editor/admin approval
        # is required for account creation. Only content submissions go
        # through editorial review.
        user = User(
            name=name,
            email=email,
            username=_slugify_username(name, email),
            role=UserRole.USER.value,
            status=UserStatus.APPROVED.value,
        )
        user.set_password(form.password.data)
        if form.theme_pref.data in VALID_THEMES:
            user.theme = form.theme_pref.data
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash(f"Welcome to the society, {user.name.split()[0]}! Your profile is ready.", "success")
        return redirect(url_for("profile.edit"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()

        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form)

        if user.status == UserStatus.REJECTED.value:
            flash("This account has been disabled. Contact the society admin.", "danger")
            return render_template("auth/login.html", form=form)

        # A guest who chose a theme before logging in keeps it on their account
        # (the client only sends theme_pref when it differs from the account's).
        if form.theme_pref.data in VALID_THEMES:
            user.theme = form.theme_pref.data
            db.session.commit()

        login_user(user, remember=form.remember_me.data)
        flash(f"Welcome back, {user.name.split()[0]}.", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.index"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("main.index"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()
        reset_url = None
        if user is not None:
            token = _reset_serializer().dumps(user.id, salt=RESET_TOKEN_SALT)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
        # No outbound email service is configured in this environment, so —
        # rather than silently failing or pretending mail was sent — the
        # (time-limited, single-purpose) reset link is handed back directly.
        # Swap this for a real mail send once SMTP/API credentials exist.
        return render_template("auth/forgot_password_sent.html", reset_url=reset_url, email=email)

    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    try:
        user_id = _reset_serializer().loads(token, salt=RESET_TOKEN_SALT, max_age=RESET_TOKEN_MAX_AGE)
    except SignatureExpired:
        flash("That reset link has expired. Request a new one.", "warning")
        return redirect(url_for("auth.forgot_password"))
    except BadSignature:
        flash("That reset link isn't valid.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = db.session.get(User, user_id)
    if user is None:
        flash("That reset link isn't valid.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Your password has been reset. Log in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form)
