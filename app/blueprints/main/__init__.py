from flask import Blueprint, render_template

from app.models import Community, Post, PostStatus, SiteConstitution
from app.services.leaderboard import top_contributors

bp = Blueprint("main", __name__, template_folder="../../templates/main")


@bp.route("/")
def index():
    communities = Community.query.order_by(Community.name).all()
    recent_posts = (
        Post.query.filter_by(status=PostStatus.PUBLISHED.value)
        .order_by(Post.created_at.desc())
        .limit(9)
        .all()
    )
    featured_post = recent_posts[0] if recent_posts else None
    feed_posts = recent_posts[1:] if recent_posts else []
    leaders = top_contributors(limit=5)
    return render_template(
        "main/index.html",
        communities=communities,
        featured_post=featured_post,
        feed_posts=feed_posts,
        leaders=leaders,
    )


@bp.route("/leaderboard")
def leaderboard():
    leaders = top_contributors(limit=25)
    return render_template("main/leaderboard.html", leaders=leaders)


@bp.route("/constitution")
def constitution():
    doc = SiteConstitution.query.order_by(SiteConstitution.version.desc()).first()
    return render_template("main/constitution.html", doc=doc)
