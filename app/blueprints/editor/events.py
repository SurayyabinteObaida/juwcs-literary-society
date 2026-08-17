from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from app.extensions import db
from app.models import Event, EventStatus, EventRegistration, RegistrationStatus
from app.services import notification_service
from app.utils import create_stored_image, UploadError

from . import bp
from .forms import EventForm


def _aware(dt):
    """Editor forms submit naive local-time datetimes; treat them as UTC so
    every stored datetime is timezone-aware and safely comparable to utcnow()."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@bp.route("/events")
def events_index():
    events = Event.query.order_by(Event.start_at.desc()).all()
    return render_template("editor/events.html", events=events)


def _apply_event_form(event, form):
    event.title = form.title.data.strip()
    event.category = form.category.data
    event.description = form.description.data.strip()
    event.venue = form.venue.data.strip()
    event.organizer = form.organizer.data.strip() if form.organizer.data else None
    event.start_at = _aware(form.start_at.data)
    event.end_at = _aware(form.end_at.data)
    event.registration_deadline = _aware(form.registration_deadline.data)
    event.capacity = form.capacity.data
    event.status = EventStatus.PUBLISHED.value if form.publish.data else EventStatus.DRAFT.value

    if form.cover_image.data and getattr(form.cover_image.data, "filename", ""):
        try:
            new_image = create_stored_image(form.cover_image.data, uploaded_by_id=current_user.id)
        except UploadError as exc:
            flash(str(exc), "danger")
            return False
        old_image = event.cover_image
        event.cover_image = new_image
        if old_image is not None:
            db.session.delete(old_image)
    return True


@bp.route("/events/new", methods=["GET", "POST"])
def event_new():
    form = EventForm()
    if form.validate_on_submit():
        event = Event(
            title=form.title.data.strip(),
            slug=Event.make_unique_slug(form.title.data),
            description="",
            venue="",
            start_at=datetime.now(timezone.utc),
            created_by_id=current_user.id,
        )
        if _apply_event_form(event, form):
            db.session.add(event)
            db.session.commit()
            flash(f'"{event.title}" saved.', "success")
            if event.status == EventStatus.PUBLISHED.value:
                notification_service.notify_event_created(event)
            return redirect(url_for("editor.events_index"))
    return render_template("editor/event_form.html", form=form, event=None)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
def event_edit(event_id):
    event = Event.query.get_or_404(event_id)
    form = EventForm(obj=event)
    if request.method == "GET":
        form.publish.data = event.status == EventStatus.PUBLISHED.value
    if form.validate_on_submit():
        was_published = event.status == EventStatus.PUBLISHED.value
        if _apply_event_form(event, form):
            db.session.commit()
            flash(f'"{event.title}" updated.', "success")
            # Only announce on the DRAFT -> PUBLISHED transition, never on a
            # re-save of an already-published event.
            if event.status == EventStatus.PUBLISHED.value and not was_published:
                notification_service.notify_event_created(event)
            return redirect(url_for("editor.events_index"))
    return render_template("editor/event_form.html", form=form, event=event)


@bp.route("/events/<int:event_id>/cancel", methods=["POST"])
def event_cancel(event_id):
    event = Event.query.get_or_404(event_id)
    event.status = EventStatus.CANCELLED.value
    db.session.commit()
    flash(f'"{event.title}" has been cancelled.', "info")
    return redirect(url_for("editor.events_index"))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
def event_delete(event_id):
    event = Event.query.get_or_404(event_id)
    title = event.title
    old_image = event.cover_image
    db.session.delete(event)
    if old_image is not None:
        db.session.delete(old_image)
    db.session.commit()
    flash(f'"{title}" deleted.', "info")
    return redirect(url_for("editor.events_index"))


@bp.route("/events/<int:event_id>/registrations")
def event_registrations(event_id):
    event = Event.query.get_or_404(event_id)
    registrations = (
        event.registrations
        .filter_by(status=RegistrationStatus.CONFIRMED.value)
        .order_by(EventRegistration.registered_at.desc())
        .all()
    )
    return render_template("editor/event_registrations.html", event=event, registrations=registrations)
