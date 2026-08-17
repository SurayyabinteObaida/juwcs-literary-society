from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, Post, ReviewStatus, VALID_THEMES, Badge
from app.blueprints.profile.forms import ProfileForm, ThemeForm
from app.services.leaderboard import top_contributors

bp = Blueprint("profile", __name__, template_folder="../../templates/profile")


def _contribution_groups(user):
    posts = user.posts.order_by(Post.created_at.desc()).all()
    return {
        "approved": [p for p in posts if p.review_status == ReviewStatus.APPROVED.value],
        "pending": [p for p in posts if p.review_status == ReviewStatus.PENDING.value],
        "rejected": [p for p in posts if p.review_status == ReviewStatus.REJECTED.value],
        "draft": [p for p in posts if p.review_status == ReviewStatus.DRAFT.value],
    }


def _profile_communities(user):
    seen = {}
    for p in user.posts.filter_by(review_status=ReviewStatus.APPROVED.value):
        if p.community and p.community.id not in seen:
            seen[p.community.id] = p.community
    return list(seen.values())


def _badge_context(user):
    all_badges = Badge.query.order_by(Badge.kind.desc(), Badge.label).all()
    earned = {ub.badge.code: ub for ub in user.badges.all()}
    return all_badges, earned


@bp.route("/me")
@login_required
def me():
    groups = _contribution_groups(current_user)
    rank = None
    for i, row in enumerate(top_contributors(limit=100), start=1):
        if row["user_id"] == current_user.id:
            rank = i
            break
    all_badges, earned_badges = _badge_context(current_user)
    return render_template(
        "profile/view.html", user=current_user, groups=groups, is_own=True, rank=rank,
        profile_communities=_profile_communities(current_user),
        all_badges=all_badges, earned_badges=earned_badges,
    )


@bp.route("/u/<username>")
def view(username):
    user = User.query.filter_by(username=username).first_or_404()
    groups = _contribution_groups(user)
    if not (current_user.is_authenticated and (current_user.id == user.id or current_user.is_admin)):
        groups["pending"] = []
        groups["rejected"] = []
        groups["draft"] = []
    rank = None
    for i, row in enumerate(top_contributors(limit=100), start=1):
        if row["user_id"] == user.id:
            rank = i
            break
    is_own = current_user.is_authenticated and current_user.id == user.id
    all_badges, earned_badges = _badge_context(user)
    return render_template(
        "profile/view.html", user=user, groups=groups, is_own=is_own, rank=rank,
        profile_communities=_profile_communities(user),
        all_badges=all_badges, earned_badges=earned_badges,
    )


@bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    form = ProfileForm(obj=current_user)
    if request.method == "GET":
        form.username.data = current_user.username or ""

    if form.validate_on_submit():
        new_username = form.username.data.strip().lower()
        clash = User.query.filter(User.username == new_username, User.id != current_user.id).first()
        if clash:
            flash("That username is already taken.", "warning")
            return render_template("profile/edit.html", form=form)

        current_user.name = form.name.data.strip()
        current_user.username = new_username
        current_user.bio = form.bio.data.strip() if form.bio.data else None
        current_user.interests = form.interests.data.strip() if form.interests.data else None
        current_user.avatar_url = form.avatar_url.data.strip() if form.avatar_url.data else None
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("profile.me"))

    return render_template("profile/edit.html", form=form)


@bp.route("/theme", methods=["GET", "POST"])
@login_required
def theme():
    form = ThemeForm(theme=current_user.display_theme)
    if form.validate_on_submit():
        if form.theme.data in VALID_THEMES:
            current_user.theme = form.theme.data
            db.session.commit()
            flash("Theme updated.", "success")
        return redirect(request.referrer or url_for("profile.me"))
    return render_template("profile/theme.html", form=form)
