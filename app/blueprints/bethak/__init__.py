from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import BethakSession, BethakEntry, BethakReaction, BethakStatus
from app.blueprints.bethak.forms import BethakSessionForm, BethakEntryForm
from app.utils import approved_required, admin_required

bp = Blueprint("bethak", __name__, template_folder="../../templates/bethak")


@bp.route("/")
def index():
    sessions = BethakSession.query.order_by(
        BethakSession.status.asc(), BethakSession.created_at.desc()
    ).all()
    return render_template("bethak/index.html", sessions=sessions)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def create():
    form = BethakSessionForm()
    if form.validate_on_submit():
        session = BethakSession(
            title=form.title.data.strip(),
            topic=form.topic.data.strip() if form.topic.data else None,
            description=form.description.data.strip() if form.description.data else None,
            created_by_id=current_user.id,
        )
        db.session.add(session)
        db.session.commit()
        flash("Bethak opened.", "success")
        return redirect(url_for("bethak.view", session_id=session.id))
    return render_template("bethak/create.html", form=form)


@bp.route("/<int:session_id>", methods=["GET", "POST"])
def view(session_id):
    session = BethakSession.query.get_or_404(session_id)
    entry_form = BethakEntryForm()

    if entry_form.validate_on_submit():
        if not current_user.is_authenticated or not current_user.is_approved:
            abort(403)
        if not session.is_open:
            flash("This bethak is closed to new entries.", "warning")
            return redirect(url_for("bethak.view", session_id=session.id))

        entry = BethakEntry(
            session_id=session.id,
            author_id=current_user.id,
            text=entry_form.text.data.strip(),
        )
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for("bethak.view", session_id=session.id))

    entries = session.entries.all()

    user_liked_ids = set()
    if current_user.is_authenticated:
        entry_ids = [e.id for e in entries]
        if entry_ids:
            liked = BethakReaction.query.filter(
                BethakReaction.entry_id.in_(entry_ids),
                BethakReaction.user_id == current_user.id,
                BethakReaction.type == "like",
            ).all()
            user_liked_ids = {r.entry_id for r in liked}

    return render_template(
        "bethak/view.html",
        session=session,
        entries=entries,
        entry_form=entry_form,
        user_liked_ids=user_liked_ids,
    )


@bp.route("/<int:session_id>/entry/<int:entry_id>/react/<reaction_type>", methods=["POST"])
@login_required
@approved_required
def react(session_id, entry_id, reaction_type):
    if reaction_type not in ("like", "report"):
        abort(400)

    entry = BethakEntry.query.get_or_404(entry_id)
    if entry.session_id != session_id:
        abort(404)

    if entry.author_id == current_user.id:
        flash("You can't react to your own entry.", "warning")
        return redirect(url_for("bethak.view", session_id=session_id))

    existing = BethakReaction.query.filter_by(
        entry_id=entry.id, user_id=current_user.id, type=reaction_type
    ).first()

    if existing:
        db.session.delete(existing)
    else:
        db.session.add(BethakReaction(entry_id=entry.id, user_id=current_user.id, type=reaction_type))
    db.session.commit()

    return redirect(url_for("bethak.view", session_id=session_id))


@bp.route("/<int:session_id>/close", methods=["POST"])
@login_required
@admin_required
def close(session_id):
    session = BethakSession.query.get_or_404(session_id)
    session.status = BethakStatus.CLOSED.value
    db.session.commit()
    flash("Bethak closed.", "info")
    return redirect(url_for("bethak.view", session_id=session_id))


@bp.route("/<int:session_id>/reopen", methods=["POST"])
@login_required
@admin_required
def reopen(session_id):
    session = BethakSession.query.get_or_404(session_id)
    session.status = BethakStatus.OPEN.value
    db.session.commit()
    flash("Bethak reopened.", "info")
    return redirect(url_for("bethak.view", session_id=session_id))
