"""
Central notification service.

Every place in the app that needs to notify a user (or a group of users)
about something goes through here — nothing calls Firebase directly from a
route. Each call:

  1. Respects the recipient's NotificationPreference (unless the type is
     unlisted in NOTIFICATION_PREFERENCE_MAP, which marks it "always on" —
     used for nothing critical enough to force on users today, but kept as
     an escape hatch).
  2. Always writes an in-app Notification row, regardless of whether push
     succeeds — the in-app center must work even when Firebase is down.
  3. Sends an FCM push to every enabled PushSubscription the user has.
  4. Never lets a Firebase failure roll back or interrupt the caller; the
     website action that triggered the notification has already committed
     by the time these functions run.

Route handlers commit their own DB changes first, then call one of the
`notify_*` helpers below.
"""
import logging

from flask import url_for

from app.extensions import db
from app.models import (
    Notification, NotificationType, NotificationPreference, NotificationDedupe,
    PushSubscription, User, UserStatus,
)
from app.services import firebase_service

logger = logging.getLogger("juwcs.notifications")


# ---------------------------------------------------------------------------
# Low-level building blocks
# ---------------------------------------------------------------------------

def _active_recipients(users):
    """Filter out unapproved/disabled accounts — they shouldn't receive
    notifications about ongoing Society activity."""
    return [u for u in users if u is not None and u.is_approved]


def notify_user(user, ntype, title, message, link=None, event=None, post=None,
                 bethak_session=None, data=None, icon=None):
    """Notify a single user: in-app row + push, respecting their preferences."""
    if user is None or not getattr(user, "is_approved", False):
        return None

    pref = NotificationPreference.get_or_create(user)
    if not pref.allows(ntype):
        return None

    notification = Notification(
        user_id=user.id,
        type=ntype,
        title=title,
        message=message,
        link=link,
        event_id=event.id if event is not None else None,
        post_id=post.id if post is not None else None,
        bethak_session_id=bethak_session.id if bethak_session is not None else None,
    )
    try:
        db.session.add(notification)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to save in-app notification for user %s", user.id)
        return None

    _push_to_user(user, title, message, link=link, data=data, icon=icon)
    return notification


def notify_users(users, ntype, title, message, link=None, event=None, post=None,
                  bethak_session=None, data=None, icon=None):
    """Notify many users at once (e.g. all approved members for a public
    announcement). Preferences are checked per-user."""
    sent = []
    for user in _active_recipients(users):
        n = notify_user(
            user, ntype, title, message, link=link, event=event, post=post,
            bethak_session=bethak_session, data=data, icon=icon,
        )
        if n is not None:
            sent.append(n)
    return sent


def _push_to_user(user, title, body, link=None, data=None, icon=None):
    subs = PushSubscription.query.filter_by(user_id=user.id, enabled=True).all()
    if not subs:
        return
    tokens = [s.fcm_token for s in subs]

    try:
        result = firebase_service.send_push_to_tokens(
            tokens, title, body, link=link, data=data, icon=icon,
        )
    except Exception:
        # Absolute last line of defense — a notification failure must never
        # propagate into the caller's request/response cycle.
        logger.exception("Push send raised unexpectedly for user %s", user.id)
        return

    if result.invalid_tokens:
        try:
            PushSubscription.query.filter(
                PushSubscription.fcm_token.in_(result.invalid_tokens)
            ).update({"enabled": False}, synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to disable stale push subscriptions")

    if result.attempted and result.success_tokens:
        try:
            from datetime import datetime, timezone
            PushSubscription.query.filter(
                PushSubscription.fcm_token.in_(result.success_tokens)
            ).update({"last_used_at": datetime.now(timezone.utc)}, synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()


def dedupe_once(kind, subject_id):
    """Returns True the first time (kind, subject_id) is seen, False on any
    repeat — used to guarantee at-most-once delivery for automatic triggers
    like event reminders, safely across concurrent processes."""
    try:
        db.session.add(NotificationDedupe(kind=kind, subject_id=str(subject_id)))
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def _all_approved_users():
    return User.query.filter_by(status=UserStatus.APPROVED.value).all()


# ---------------------------------------------------------------------------
# Domain-specific helpers — called from routes after a successful DB commit
# ---------------------------------------------------------------------------

def notify_event_created(event):
    """Broadcast a newly-published event to every eligible (approved) member
    who hasn't opted out of event notifications."""
    when = event.start_at.strftime("%B %d • %I:%M %p").replace(" 0", " ")
    return notify_users(
        _all_approved_users(),
        NotificationType.EVENT_CREATED.value,
        "📅 New Literary Event",
        f"{event.title} has been announced. {when}.",
        link=url_for("events.detail", slug=event.slug),
        event=event,
    )


def notify_event_registration(registration):
    """Private confirmation — the registering user only."""
    event = registration.event
    when = event.start_at.strftime("%B %d • %I:%M %p").replace(" 0", " ")
    return notify_user(
        registration.user,
        NotificationType.EVENT_REGISTRATION.value,
        "✅ Registration Confirmed",
        f"You are registered for {event.title}. {when}.",
        link=url_for("events.detail", slug=event.slug),
        event=event,
    )


def notify_event_reminder(event, hours_before):
    """Send a reminder to every user with a confirmed registration for
    `event`. `hours_before` is 24 or 1 — controls copy + dedupe key +
    notification type. Idempotent: safe to call repeatedly (e.g. from a
    periodic cron tick) — each (event, user) pair fires at most once."""
    from app.models import RegistrationStatus

    kind = f"event_reminder_{hours_before}h"
    ntype = (
        NotificationType.EVENT_REMINDER.value if hours_before == 24
        else NotificationType.EVENT_STARTING.value
    )

    sent = []
    registrations = event.registrations.filter_by(status=RegistrationStatus.CONFIRMED.value).all()
    for reg in registrations:
        if not dedupe_once(kind, f"event:{event.id}:user:{reg.user_id}"):
            continue
        if hours_before == 24:
            title, msg = "📅 Event Tomorrow", f"{event.title} is happening tomorrow at {event.start_at.strftime('%I:%M %p').lstrip('0')}."
        else:
            title, msg = "⏰ Starting Soon", f"{event.title} starts in 1 hour."
        n = notify_user(
            reg.user, ntype, title, msg, link=url_for("events.detail", slug=event.slug), event=event,
        )
        if n is not None:
            sent.append(n)
    return sent


def notify_bethak_opened(session):
    """Broadcast — a Digital Bethak just transitioned to OPEN."""
    return notify_users(
        _all_approved_users(),
        NotificationType.BETHAK_OPENED.value,
        "🪶 Digital Bethak is Open",
        "The Digital Bethak is open now. Come share your poetry, thoughts and ideas.",
        link=url_for("bethak.view", session_id=session.id),
        bethak_session=session,
    )


def notify_post_approved(post):
    return notify_user(
        post.author,
        NotificationType.POST_APPROVED.value,
        "✨ Your Submission Was Published",
        "Your submission has been approved by the Editor and is now published.",
        link=url_for("posts.view", post_id=post.id),
        post=post,
    )


def notify_post_rejected(post):
    return notify_user(
        post.author,
        NotificationType.POST_REJECTED.value,
        "Your Submission Update",
        "Your submission was not approved. Please review the Editor's feedback.",
        link=url_for("posts.view", post_id=post.id),
        post=post,
    )


def notify_changes_requested(post):
    return notify_user(
        post.author,
        NotificationType.POST_CHANGES_REQUESTED.value,
        "✏️ Changes Requested",
        "The Editor has requested changes to your submission.",
        link=url_for("posts.view", post_id=post.id),
        post=post,
    )


def notify_editor_pick(highlight):
    return notify_users(
        _all_approved_users(),
        NotificationType.EDITOR_PICK.value,
        "✨ New Editor's Pick",
        f'Discover the latest featured literary work: "{highlight.title}".',
        link=url_for("main.highlight_detail", slug=highlight.slug),
    )


def notify_test(user, message="Test notification from JUWCS"):
    """Admin-only test send — targets only the calling admin's own devices,
    never broadcast to other users."""
    notification = Notification(
        user_id=user.id,
        type=NotificationType.SYSTEM.value,
        title="🔔 Test Notification",
        message=message,
        link="/",
    )
    db.session.add(notification)
    db.session.commit()
    _push_to_user(user, "🔔 Test Notification", message, link="/")
    return notification
