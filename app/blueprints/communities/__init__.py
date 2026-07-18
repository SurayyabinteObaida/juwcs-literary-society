from flask import Blueprint, render_template, request
from flask_login import current_user

from app.models import Community, Post, PostStatus, CommunityCategory

bp = Blueprint("communities", __name__, template_folder="../../templates/communities")


@bp.route("/")
def index():
    communities = Community.query.order_by(Community.name).all()
    return render_template("communities/index.html", communities=communities)


@bp.route("/<slug>")
def detail(slug):
    community = Community.query.filter_by(slug=slug).first_or_404()

    query = Post.query.filter_by(community_id=community.id, status=PostStatus.PUBLISHED.value)

    category_id = request.args.get("category", type=int)
    if category_id:
        query = query.filter(Post.categories.any(CommunityCategory.id == category_id))

    posts = query.order_by(Post.created_at.desc()).all()

    return render_template(
        "communities/detail.html",
        community=community,
        posts=posts,
        active_category_id=category_id,
    )
