from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Event, EventStatus, EventRegistration, RegistrationStatus
from app.services import notification_service
from app.utils import approved_required

bp = Blueprint("events", __name__, template_folder="../../templates/events")


def _published_query():
    return Event.query.filter_by(status=EventStatus.PUBLISHED.value)


@bp.route("/")
def index():
    now = datetime.now(timezone.utc)
    upcoming = (
        _published_query()
        .filter(Event.start_at >= now)
        .order_by(Event.start_at.asc())
        .all()
    )
    past = (
        _published_query()
        .filter(Event.start_at < now)
        .order_by(Event.start_at.desc())
        .limit(6)
        .all()
    )
    featured = upcoming[0] if upcoming else None
    rest = upcoming[1:] if upcoming else []
    return render_template("events/index.html", featured=featured, events=rest, past=past)


@bp.route("/<slug>")
def detail(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    if not event.is_published and not (current_user.is_authenticated and current_user.is_editor_or_admin):
        abort(404)
    my_registration = event.registration_for(current_user)
    return render_template("events/detail.html", event=event, my_registration=my_registration)


@bp.route("/<slug>/register", methods=["POST"])
@login_required
@approved_required
def register(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()

    if not event.is_published:
        abort(404)

    existing = event.registrations.filter_by(user_id=current_user.id).first()
    if existing and existing.status == RegistrationStatus.CONFIRMED.value:
        flash("You're already registered for this event.", "info")
        return redirect(url_for("events.confirmation", slug=event.slug, reference=existing.reference))

    if event.is_cancelled:
        flash("This event has been cancelled.", "warning")
        return redirect(url_for("events.detail", slug=slug))

    if event.registration_closed:
        flash("Registration is closed for this event.", "warning")
        return redirect(url_for("events.detail", slug=slug))

    if event.is_full:
        flash("This event is fully booked.", "warning")
        return redirect(url_for("events.detail", slug=slug))

    try:
        if existing:
            # Re-activate a previously cancelled registration instead of violating
            # the unique (event_id, user_id) constraint.
            existing.status = RegistrationStatus.CONFIRMED.value
            existing.registered_at = datetime.now(timezone.utc)
            existing.reference = EventRegistration.make_reference()
            registration = existing
        else:
            registration = EventRegistration(
                event_id=event.id,
                user_id=current_user.id,
                reference=EventRegistration.make_reference(),
            )
            db.session.add(registration)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("We couldn't complete your registration — please try again.", "danger")
        return redirect(url_for("events.detail", slug=slug))

    flash("You're registered!", "success")
    notification_service.notify_event_registration(registration)
    return redirect(url_for("events.confirmation", slug=event.slug, reference=registration.reference))


@bp.route("/<slug>/confirmation/<reference>")
@login_required
def confirmation(slug, reference):
    event = Event.query.filter_by(slug=slug).first_or_404()
    registration = event.registrations.filter_by(reference=reference).first_or_404()
    if registration.user_id != current_user.id and not current_user.is_editor_or_admin:
        abort(403)
    return render_template("events/confirmation.html", event=event, registration=registration)


@bp.route("/<slug>/cancel", methods=["POST"])
@login_required
def cancel_registration(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    registration = event.registrations.filter_by(
        user_id=current_user.id, status=RegistrationStatus.CONFIRMED.value,
    ).first()
    if registration:
        registration.status = RegistrationStatus.CANCELLED.value
        db.session.commit()
        flash("Your registration has been cancelled.", "info")
    return redirect(url_for("events.detail", slug=slug))
