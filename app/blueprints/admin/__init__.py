from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from app.extensions import db
from app.models import User, UserStatus, UserRole, Post, PostStatus, ReviewStatus, Reaction, ReactionType, Community
from app.utils import admin_required

bp = Blueprint("admin", __name__, template_folder="../../templates/admin")


@bp.before_request
def guard():
    """Every route in this blueprint requires an authenticated admin."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.path))
    if not current_user.is_admin:
        abort(403)


@bp.route("/")
def dashboard():
    stats = {
        "members": User.query.filter_by(role=UserRole.USER.value).count(),
        "editors": User.query.filter_by(role=UserRole.EDITOR.value).count(),
        "admins": User.query.filter_by(role=UserRole.ADMIN.value).count(),
        "communities": Community.query.count(),
        "pending_content": Post.query.filter_by(review_status=ReviewStatus.PENDING.value).count(),
        "approved_content": Post.query.filter_by(review_status=ReviewStatus.APPROVED.value).count(),
        "rejected_content": Post.query.filter_by(review_status=ReviewStatus.REJECTED.value).count(),
    }
    reported_posts = (
        db.session.query(Post)
        .join(Reaction, Reaction.post_id == Post.id)
        .filter(Reaction.type == ReactionType.REPORT.value, Post.status == PostStatus.PUBLISHED.value)
        .distinct()
        .all()
    )
    return render_template("admin/dashboard.html", stats=stats, reported_posts=reported_posts)


@bp.route("/users")
def users():
    role_filter = request.args.get("role")
    query = User.query
    if role_filter in (UserRole.USER.value, UserRole.EDITOR.value, UserRole.ADMIN.value):
        query = query.filter_by(role=role_filter)
    all_users = query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users, role_filter=role_filter)


@bp.route("/users/<int:user_id>/make-editor", methods=["POST"])
def make_editor(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash("Admins already have full editorial authority.", "warning")
        return redirect(url_for("admin.users"))
    user.role = UserRole.EDITOR.value
    db.session.commit()
    flash(f"{user.name} is now an Editor.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/remove-editor", methods=["POST"])
def remove_editor(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == UserRole.EDITOR.value:
        user.role = UserRole.USER.value
        db.session.commit()
        flash(f"{user.name}'s Editor role was removed.", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/disable", methods=["POST"])
def disable_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash("Admin accounts cannot be disabled here.", "warning")
        return redirect(url_for("admin.users"))
    user.status = UserStatus.REJECTED.value
    db.session.commit()
    flash(f"{user.name}'s account was disabled.", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/enable", methods=["POST"])
def enable_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = UserStatus.APPROVED.value
    db.session.commit()
    flash(f"{user.name}'s account was re-enabled.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/content")
def content():
    status_filter = request.args.get("status", "pending")
    query = Post.query
    if status_filter in (ReviewStatus.PENDING.value, ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value, ReviewStatus.DRAFT.value):
        query = query.filter_by(review_status=status_filter)
    posts = query.order_by(Post.created_at.desc()).limit(100).all()
    return render_template("admin/content.html", posts=posts, status_filter=status_filter)


@bp.route("/posts/<int:post_id>/remove", methods=["POST"])
def remove_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.status = PostStatus.REMOVED.value
    db.session.commit()
    flash("Post removed.", "info")
    return redirect(request.referrer or url_for("admin.dashboard"))


@bp.route("/posts/<int:post_id>/dismiss-reports", methods=["POST"])
def dismiss_reports(post_id):
    Reaction.query.filter_by(post_id=post_id, type=ReactionType.REPORT.value).delete()
    db.session.commit()
    flash("Reports dismissed.", "info")
    return redirect(request.referrer or url_for("admin.dashboard"))
