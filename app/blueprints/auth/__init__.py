from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models import User, UserStatus
from app.blueprints.auth.forms import RegistrationForm, LoginForm

bp = Blueprint("auth", __name__, template_folder="../../templates/auth")


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

        user = User(
            name=form.name.data.strip(),
            email=form.email.data.lower().strip(),
            status=UserStatus.PENDING.value,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash(
            "Registration request submitted. You'll be able to log in once "
            "the society admin approves your account.",
            "success",
        )
        return redirect(url_for("auth.login"))

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

        if user.status == UserStatus.PENDING.value:
            flash("Your registration is still pending admin approval.", "info")
            return render_template("auth/login.html", form=form)

        if user.status == UserStatus.REJECTED.value:
            flash("Your registration request was not approved. Contact the society admin.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(user)
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.index"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("main.index"))
