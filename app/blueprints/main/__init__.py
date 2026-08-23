from datetime import datetime, timezone

from flask import Blueprint, render_template, abort

from app.extensions import db
from app.models import (
    Community, Post, PostStatus, ReviewStatus, SiteConstitution, User, UserStatus,
    Event, EventStatus, WeeklyHighlight,
)
from app.services.leaderboard import top_contributors

bp = Blueprint("main", __name__, template_folder="../../templates/main")


def _public_posts_query():
    return Post.query.filter_by(
        status=PostStatus.PUBLISHED.value, review_status=ReviewStatus.APPROVED.value,
    )


@bp.route("/")
def index():
    communities = Community.query.order_by(Community.name).all()
    now = datetime.now(timezone.utc)

    upcoming_events = (
        Event.query.filter(Event.status == EventStatus.PUBLISHED.value, Event.start_at >= now)
        .order_by(Event.start_at.asc())
        .limit(4)
        .all()
    )
    featured_event = upcoming_events[0] if upcoming_events else None
    other_events = upcoming_events[1:] if upcoming_events else []

    weekly_highlight = (
        WeeklyHighlight.query.filter_by(published=True)
        .order_by(WeeklyHighlight.published_at.desc())
        .first()
    )

    featured_post = (
        _public_posts_query().order_by(Post.created_at.desc()).first()
    )

    stats = {
        "communities": len(communities),
        "members": User.query.filter_by(status=UserStatus.APPROVED.value).count(),
        "posts": _public_posts_query().count(),
        "events": Event.query.filter(Event.status == EventStatus.PUBLISHED.value, Event.start_at >= now).count(),
    }
    return render_template(
        "main/landing.html",
        communities=communities,
        stats=stats,
        featured_event=featured_event,
        other_events=other_events,
        weekly_highlight=weekly_highlight,
        featured_post=featured_post,
    )


@bp.route("/highlights")
def highlights_gallery():
    highlights = (
        WeeklyHighlight.query.filter_by(published=True)
        .order_by(WeeklyHighlight.published_at.desc())
        .all()
    )
    return render_template("main/highlights_gallery.html", highlights=highlights)


@bp.route("/highlights/<slug>")
def highlight_detail(slug):
    highlight = WeeklyHighlight.query.filter_by(slug=slug).first_or_404()
    if not highlight.published:
        abort(404)
    return render_template("main/highlight_detail.html", highlight=highlight)


@bp.route("/feed")
def feed():
    communities = Community.query.order_by(Community.name).all()
    recent_posts = (
        _public_posts_query()
        .order_by(Post.created_at.desc())
        .limit(9)
        .all()
    )
    featured_post = recent_posts[0] if recent_posts else None
    feed_posts = recent_posts[1:] if recent_posts else []
    leaders = top_contributors(limit=5)
    return render_template(
        "main/feed.html",
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
