from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash
from flask_login import current_user

from app.extensions import db
from app.models import WeeklyHighlight
from app.services import notification_service
from app.utils import create_stored_image, UploadError

from . import bp
from .forms import HighlightForm


@bp.route("/highlights")
def highlights_index():
    highlights = WeeklyHighlight.query.order_by(WeeklyHighlight.created_at.desc()).all()
    return render_template("editor/highlights.html", highlights=highlights)


@bp.route("/highlights/new", methods=["GET", "POST"])
def highlight_new():
    form = HighlightForm()
    if form.validate_on_submit():
        try:
            new_image = create_stored_image(form.image.data, uploaded_by_id=current_user.id)
        except UploadError as exc:
            flash(str(exc), "danger")
            return render_template("editor/highlight_form.html", form=form, highlight=None)

        highlight = WeeklyHighlight(
            title=form.title.data.strip(),
            slug=WeeklyHighlight.make_unique_slug(form.title.data),
            description=form.description.data.strip(),
            editorial_note=(form.editorial_note.data or "").strip() or None,
            category=form.category.data,
            contributor_name=(form.contributor_name.data or "").strip() or None,
            image=new_image,
            published=form.publish.data,
            published_at=datetime.now(timezone.utc) if form.publish.data else None,
            created_by_id=current_user.id,
        )
        db.session.add(highlight)
        db.session.commit()
        flash(f'"{highlight.title}" saved.', "success")
        if highlight.published:
            notification_service.notify_editor_pick(highlight)
        return redirect(url_for("editor.highlights_index"))
    return render_template("editor/highlight_form.html", form=form, highlight=None)


@bp.route("/highlights/<int:highlight_id>/edit", methods=["GET", "POST"])
def highlight_edit(highlight_id):
    highlight = WeeklyHighlight.query.get_or_404(highlight_id)
    form = HighlightForm(obj=highlight)
    if form.validate_on_submit():
        highlight.title = form.title.data.strip()
        highlight.description = form.description.data.strip()
        highlight.editorial_note = (form.editorial_note.data or "").strip() or None
        highlight.category = form.category.data
        highlight.contributor_name = (form.contributor_name.data or "").strip() or None

        if form.image.data and getattr(form.image.data, "filename", ""):
            try:
                new_image = create_stored_image(form.image.data, uploaded_by_id=current_user.id)
            except UploadError as exc:
                flash(str(exc), "danger")
                return render_template("editor/highlight_form.html", form=form, highlight=highlight)
            old_image = highlight.image
            highlight.image = new_image
            if old_image is not None:
                db.session.delete(old_image)

        was_published = highlight.published
        highlight.published = form.publish.data
        if highlight.published and not was_published:
            highlight.published_at = datetime.now(timezone.utc)

        db.session.commit()
        flash(f'"{highlight.title}" updated.', "success")
        if highlight.published and not was_published:
            notification_service.notify_editor_pick(highlight)
        return redirect(url_for("editor.highlights_index"))
    return render_template("editor/highlight_form.html", form=form, highlight=highlight)


@bp.route("/highlights/<int:highlight_id>/unpublish", methods=["POST"])
def highlight_unpublish(highlight_id):
    highlight = WeeklyHighlight.query.get_or_404(highlight_id)
    highlight.published = False
    db.session.commit()
    flash(f'"{highlight.title}" unpublished.', "info")
    return redirect(url_for("editor.highlights_index"))


@bp.route("/highlights/<int:highlight_id>/delete", methods=["POST"])
def highlight_delete(highlight_id):
    highlight = WeeklyHighlight.query.get_or_404(highlight_id)
    title = highlight.title
    old_image = highlight.image
    db.session.delete(highlight)
    if old_image is not None:
        db.session.delete(old_image)
    db.session.commit()
    flash(f'"{title}" deleted.', "info")
    return redirect(url_for("editor.highlights_index"))
