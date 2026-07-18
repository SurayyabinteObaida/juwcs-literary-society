from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from app.extensions import db
from app.models import User, UserStatus, Post, PostStatus, Reaction, ReactionType

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
    pending_count = User.query.filter_by(status=UserStatus.PENDING.value).count()
    reported_posts = (
        db.session.query(Post)
        .join(Reaction, Reaction.post_id == Post.id)
        .filter(Reaction.type == ReactionType.REPORT.value, Post.status == PostStatus.PUBLISHED.value)
        .distinct()
        .all()
    )
    return render_template("admin/dashboard.html", pending_count=pending_count, reported_posts=reported_posts)


@bp.route("/users/pending")
def pending_users():
    users = User.query.filter_by(status=UserStatus.PENDING.value).order_by(User.created_at).all()
    return render_template("admin/pending_users.html", users=users)


@bp.route("/users/<int:user_id>/approve", methods=["POST"])
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = UserStatus.APPROVED.value
    db.session.commit()
    flash(f"{user.name} approved.", "success")
    return redirect(url_for("admin.pending_users"))


@bp.route("/users/<int:user_id>/reject", methods=["POST"])
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = UserStatus.REJECTED.value
    db.session.commit()
    flash(f"{user.name} rejected.", "info")
    return redirect(url_for("admin.pending_users"))


@bp.route("/posts/<int:post_id>/remove", methods=["POST"])
def remove_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.status = PostStatus.REMOVED.value
    db.session.commit()
    flash("Post removed.", "info")
    return redirect(url_for("admin.dashboard"))


@bp.route("/posts/<int:post_id>/dismiss-reports", methods=["POST"])
def dismiss_reports(post_id):
    Reaction.query.filter_by(post_id=post_id, type=ReactionType.REPORT.value).delete()
    db.session.commit()
    flash("Reports dismissed.", "info")
    return redirect(url_for("admin.dashboard"))
