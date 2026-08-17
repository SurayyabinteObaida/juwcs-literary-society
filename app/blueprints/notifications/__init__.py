from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf, ValidationError

from app.extensions import db
from app.models import PushSubscription, Notification, NotificationPreference
from app.services import notification_service
from app.utils import admin_required
from .forms import NotificationPreferencesForm

bp = Blueprint("notifications", __name__, template_folder="../../templates/notifications")


def _check_csrf():
    """Manual CSRF check for JSON/fetch endpoints (this project doesn't run
    CSRFProtect app-wide, so form-based routes get CSRF via FlaskForm and
    these API routes get it here, from the same csrf_token() the rest of
    the site already renders)."""
    token = (
        request.headers.get("X-CSRFToken")
        or request.form.get("csrf_token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
    )
    try:
        validate_csrf(token)
        return True
    except ValidationError:
        return False


@bp.route("/config.json")
@login_required
def config_json():
    """Public (non-secret) Firebase web config + VAPID key, for the frontend
    initializer. Requires login so we don't hand it out to anonymous scrapers
    for no reason, even though none of this is a real secret."""
    return jsonify({
        "firebaseConfig": current_app.config["FIREBASE_WEB_CONFIG"],
        "vapidKey": current_app.config["FIREBASE_VAPID_PUBLIC_KEY"],
    })


@bp.route("/register", methods=["POST"])
@login_required
def register():
    if not _check_csrf():
        return jsonify({"error": "invalid_csrf"}), 400

    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"error": "missing_token"}), 400

    sub = PushSubscription.query.filter_by(fcm_token=token).first()
    now = datetime.now(timezone.utc)

    if sub is None:
        sub = PushSubscription(fcm_token=token, user_id=current_user.id)
        db.session.add(sub)
    else:
        # Same browser, possibly a different account now logged in
        # (see requirement: safe account switching on a shared browser).
        sub.user_id = current_user.id

    sub.browser = (payload.get("browser") or "")[:60] or None
    sub.device = (payload.get("device") or "")[:60] or None
    sub.platform = (payload.get("platform") or "")[:60] or None
    sub.user_agent = (request.headers.get("User-Agent") or "")[:400] or None
    sub.enabled = True
    sub.updated_at = now
    sub.last_used_at = now

    db.session.commit()
    NotificationPreference.get_or_create(current_user)
    db.session.commit()

    return jsonify({"status": "ok"})


@bp.route("/unregister", methods=["POST"])
@login_required
def unregister():
    if not _check_csrf():
        return jsonify({"error": "invalid_csrf"}), 400

    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"error": "missing_token"}), 400

    sub = PushSubscription.query.filter_by(fcm_token=token, user_id=current_user.id).first()
    if sub is not None:
        sub.enabled = False
        db.session.commit()
    return jsonify({"status": "ok"})


@bp.route("/status")
@login_required
def status():
    """Whether *this* browser (by token, sent as a query param once the
    frontend has one cached) is currently registered — used on page load to
    decide whether to show the opt-in prompt or render as already-enabled."""
    token = (request.args.get("token") or "").strip()
    registered = False
    if token:
        registered = PushSubscription.query.filter_by(
            fcm_token=token, user_id=current_user.id, enabled=True,
        ).first() is not None
    return jsonify({"registered": registered})


@bp.route("/list")
@login_required
def list_notifications():
    limit = min(int(request.args.get("limit", 20)), 50)
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({
        "unread_count": unread_count,
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "icon": n.icon,
                "title": n.title,
                "message": n.message,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in items
        ],
    })


@bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    if not _check_csrf():
        return jsonify({"error": "invalid_csrf"}), 400
    n = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
    if n is not None and not n.is_read:
        n.is_read = True
        db.session.commit()
    return jsonify({"status": "ok"})


@bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    if not _check_csrf():
        return jsonify({"error": "invalid_csrf"}), 400
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"status": "ok"})


@bp.route("/preferences", methods=["GET", "POST"])
@login_required
def preferences():
    pref = NotificationPreference.get_or_create(current_user)
    db.session.commit()

    form = NotificationPreferencesForm(obj=pref)
    if form.validate_on_submit():
        form.populate_obj(pref)
        db.session.commit()
        flash("Notification preferences updated.", "success")
        return redirect(url_for("notifications.preferences"))

    return render_template("notifications/preferences.html", form=form)


@bp.route("/test", methods=["POST"])
@login_required
@admin_required
def send_test():
    """Admin-only. Sends only to the currently logged-in admin's own
    registered browsers/devices — never to other users."""
    if not _check_csrf():
        flash("Your session expired — please try again.", "warning")
        return redirect(request.referrer or url_for("admin.dashboard"))
    message = (request.form.get("message") or "Test notification from JUWCS").strip()[:500]
    notification_service.notify_test(current_user, message=message)
    flash("Test notification sent to your registered devices.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))
