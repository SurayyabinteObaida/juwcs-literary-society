from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Post, Community, Comment, Reaction, ReactionType, PostStatus, ReviewStatus
from app.blueprints.posts.forms import PostForm, CommentForm
from app.services.badges import evaluate_user_badges
from app.utils import approved_required

bp = Blueprint("posts", __name__, template_folder="../../templates/posts")


@bp.route("/community/<slug>/new", methods=["GET", "POST"])
@login_required
@approved_required
def create(slug):
    community = Community.query.filter_by(slug=slug).first_or_404()
    form = PostForm()
    form.categories.choices = [(c.id, c.label) for c in community.categories]

    if form.validate_on_submit():
        is_draft = form.save_draft.data and not form.submit.data

        post = Post(
            community_id=community.id,
            author_id=current_user.id,
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            content_type=form.content_type.data,
            review_status=ReviewStatus.DRAFT.value if is_draft else ReviewStatus.PENDING.value,
            submitted_at=None if is_draft else datetime.now(timezone.utc),
        )
        selected_ids = set(form.categories.data)
        post.categories = [c for c in community.categories if c.id in selected_ids]
        db.session.add(post)
        db.session.commit()

        if is_draft:
            flash("Draft saved. You can submit it for review any time from your profile.", "info")
            return redirect(url_for("profile.me"))

        flash("Your submission has been sent to an Editor for review.", "success")
        return redirect(url_for("profile.me"))

    return render_template("posts/create.html", form=form, community=community)


@bp.route("/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and not current_user.is_admin:
        abort(403)
    # Only drafts and rejected submissions can be edited/resubmitted.
    if post.review_status not in (ReviewStatus.DRAFT.value, ReviewStatus.REJECTED.value):
        flash("Only drafts and rejected submissions can be edited.", "warning")
        return redirect(url_for("posts.view", post_id=post.id))

    community = post.community
    form = PostForm(obj=post)
    form.categories.choices = [(c.id, c.label) for c in community.categories]
    if request.method == "GET":
        form.categories.data = [c.id for c in post.categories]

    if form.validate_on_submit():
        is_draft = form.save_draft.data and not form.submit.data

        post.title = form.title.data.strip()
        post.body = form.body.data.strip()
        post.content_type = form.content_type.data
        selected_ids = set(form.categories.data)
        post.categories = [c for c in community.categories if c.id in selected_ids]

        if is_draft:
            post.review_status = ReviewStatus.DRAFT.value
        else:
            post.review_status = ReviewStatus.PENDING.value
            post.submitted_at = datetime.now(timezone.utc)
            post.rejection_reason = None
            post.reviewed_at = None
            post.reviewed_by_id = None

        db.session.commit()

        flash("Saved as draft." if is_draft else "Resubmitted for editorial review.", "success")
        return redirect(url_for("profile.me"))

    return render_template("posts/create.html", form=form, community=community, editing=True, post=post)


@bp.route("/<int:post_id>", methods=["GET", "POST"])
def view(post_id):
    post = Post.query.get_or_404(post_id)

    is_owner_or_staff = current_user.is_authenticated and (
        current_user.id == post.author_id or current_user.is_editor_or_admin
    )

    if not post.is_public and not is_owner_or_staff:
        abort(404)
    if post.status == PostStatus.REMOVED.value and not (current_user.is_authenticated and current_user.is_admin):
        abort(404)

    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not post.is_public:
            abort(403)
        if not current_user.is_authenticated or not current_user.is_approved:
            abort(403)
        comment = Comment(post_id=post.id, author_id=current_user.id, body=comment_form.body.data.strip())
        db.session.add(comment)
        db.session.commit()
        flash("Comment added.", "success")
        return redirect(url_for("posts.view", post_id=post.id))

    user_reaction_types = set()
    if current_user.is_authenticated:
        user_reaction_types = {
            r.type for r in Reaction.query.filter_by(post_id=post.id, user_id=current_user.id).all()
        }

    return render_template(
        "posts/view.html",
        post=post,
        comment_form=comment_form,
        like_count=post.reaction_count(ReactionType.LIKE.value),
        report_count=post.reaction_count(ReactionType.REPORT.value),
        user_has_liked="like" in user_reaction_types,
        user_has_reported="report" in user_reaction_types,
    )


@bp.route("/<int:post_id>/react/<reaction_type>", methods=["POST"])
@login_required
@approved_required
def react(post_id, reaction_type):
    if reaction_type not in (ReactionType.LIKE.value, ReactionType.REPORT.value):
        abort(400)

    post = Post.query.get_or_404(post_id)
    if not post.is_public:
        abort(404)

    if post.author_id == current_user.id:
        flash("You can't react to your own post.", "warning")
        return redirect(url_for("posts.view", post_id=post.id))

    existing = Reaction.query.filter_by(
        post_id=post.id, user_id=current_user.id, type=reaction_type
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash(f"Removed your {reaction_type}.", "info")
    else:
        db.session.add(Reaction(post_id=post.id, user_id=current_user.id, type=reaction_type))
        db.session.commit()

        evaluate_user_badges(post.author, triggered_by_post=post)

        flash(f"Post {reaction_type}d." if reaction_type == "like" else "Post reported. An editor will review it.", "success")

    return redirect(url_for("posts.view", post_id=post.id))
