from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from app.extensions import db
from app.models import Post, ReviewStatus, Event, EventStatus, EventRegistration, WeeklyHighlight
from app.services.badges import evaluate_user_badges
from app.services import notification_service
from app.utils import editor_required

bp = Blueprint("editor", __name__, template_folder="../../templates/editor")


@bp.before_request
def guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.path))
    if not current_user.is_editor_or_admin:
        abort(403)


@bp.route("/")
def dashboard():
    pending = (
        Post.query.filter_by(review_status=ReviewStatus.PENDING.value)
        .order_by(Post.submitted_at.asc().nullsfirst())
        .all()
    )
    recently_reviewed = (
        Post.query.filter(Post.review_status.in_([ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value]))
        .order_by(Post.reviewed_at.desc().nullslast())
        .limit(15)
        .all()
    )

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    upcoming_events = (
        Event.query.filter(
            Event.status == EventStatus.PUBLISHED.value, Event.start_at >= now,
        ).order_by(Event.start_at.asc()).limit(6).all()
    )
    published_pieces_count = Post.query.filter_by(review_status=ReviewStatus.APPROVED.value).count()
    total_registrations = EventRegistration.query.count()
    highlights_count = WeeklyHighlight.query.filter_by(published=True).count()

    stats = {
        "pending": len(pending),
        "published_pieces": published_pieces_count,
        "upcoming_events": Event.query.filter(
            Event.status == EventStatus.PUBLISHED.value, Event.start_at >= now,
        ).count(),
        "event_registrations": total_registrations,
        "highlights": highlights_count,
    }

    return render_template(
        "editor/dashboard.html",
        pending=pending,
        recently_reviewed=recently_reviewed,
        stats=stats,
        upcoming_events=upcoming_events,
    )


@bp.route("/submissions/<int:post_id>")
def review(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template("editor/review.html", post=post)


@bp.route("/submissions/<int:post_id>/approve", methods=["POST"])
def approve(post_id):
    from datetime import datetime, timezone

    post = Post.query.get_or_404(post_id)
    if post.review_status not in (ReviewStatus.PENDING.value, ReviewStatus.REJECTED.value):
        flash("Only pending submissions can be approved.", "warning")
        return redirect(url_for("editor.dashboard"))

    post.review_status = ReviewStatus.APPROVED.value
    post.rejection_reason = None
    post.reviewed_at = datetime.now(timezone.utc)
    post.reviewed_by_id = current_user.id
    db.session.commit()

    notification_service.notify_post_approved(post)

    newly_awarded = evaluate_user_badges(post.author, triggered_by_post=None)
    for code in newly_awarded:
        flash(f"{post.author.name} earned a new badge: {code.replace('_', ' ').title()}", "info")

    flash(f'"{post.title}" approved and published.', "success")
    return redirect(url_for("editor.dashboard"))


@bp.route("/submissions/<int:post_id>/reject", methods=["POST"])
def reject(post_id):
    from datetime import datetime, timezone

    post = Post.query.get_or_404(post_id)
    if post.review_status not in (ReviewStatus.PENDING.value, ReviewStatus.APPROVED.value):
        flash("Only pending submissions can be rejected.", "warning")
        return redirect(url_for("editor.dashboard"))

    reason = (request.form.get("reason") or "").strip()
    post.review_status = ReviewStatus.REJECTED.value
    post.rejection_reason = reason or "Did not meet the community's editorial guidelines."
    post.reviewed_at = datetime.now(timezone.utc)
    post.reviewed_by_id = current_user.id
    db.session.commit()

    notification_service.notify_post_rejected(post)

    flash(f'"{post.title}" rejected with feedback sent to the author.', "info")
    return redirect(url_for("editor.dashboard"))


@bp.route("/submissions/<int:post_id>/request-changes", methods=["POST"])
def request_changes(post_id):
    """Ask the author to revise a pending submission without formally
    rejecting it — the post stays PENDING, but the author is notified with
    the Editor's feedback and can resubmit."""
    from datetime import datetime, timezone

    post = Post.query.get_or_404(post_id)
    if post.review_status != ReviewStatus.PENDING.value:
        flash("Changes can only be requested on a pending submission.", "warning")
        return redirect(url_for("editor.dashboard"))

    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Add a note explaining what needs to change.", "warning")
        return redirect(url_for("editor.review", post_id=post.id))

    post.rejection_reason = reason
    post.reviewed_at = datetime.now(timezone.utc)
    post.reviewed_by_id = current_user.id
    db.session.commit()

    notification_service.notify_changes_requested(post)

    flash(f'Requested changes on "{post.title}" — the author has been notified.', "info")
    return redirect(url_for("editor.dashboard"))


# Split out for readability — these modules attach more routes to `bp`.
from . import events as _editor_events  # noqa: E402,F401
from . import highlights as _editor_highlights  # noqa: E402,F401
