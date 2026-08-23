"""
Top Contributors leaderboard.

Computed live (no stored table) — fine at this scale. Score formula:
    score = posts * POST_WEIGHT + likes_received * LIKE_WEIGHT - reports_received * REPORT_WEIGHT
"""
from sqlalchemy import func, case

from app.extensions import db
from app.models import User, Post, Reaction, ReactionType, UserStatus, ReviewStatus, PostStatus

POST_WEIGHT = 3
LIKE_WEIGHT = 1
REPORT_WEIGHT = 2


def top_contributors(limit=10):
    likes = func.sum(case((Reaction.type == ReactionType.LIKE.value, 1), else_=0))
    reports = func.sum(case((Reaction.type == ReactionType.REPORT.value, 1), else_=0))
    post_count = func.count(func.distinct(Post.id))

    query = (
        db.session.query(
            User.id,
            User.name,
            post_count.label("post_count"),
            func.coalesce(likes, 0).label("likes_received"),
            func.coalesce(reports, 0).label("reports_received"),
        )
        .join(Post, Post.author_id == User.id)
        .outerjoin(Reaction, Reaction.post_id == Post.id)
        .filter(User.status == UserStatus.APPROVED.value)
        .filter(Post.review_status == ReviewStatus.APPROVED.value)
        .filter(Post.status == PostStatus.PUBLISHED.value)
        .group_by(User.id, User.name)
    )

    rows = []
    for row in query.all():
        score = (
            row.post_count * POST_WEIGHT
            + row.likes_received * LIKE_WEIGHT
            - row.reports_received * REPORT_WEIGHT
        )
        rows.append({
            "user_id": row.id,
            "name": row.name,
            "post_count": row.post_count,
            "likes_received": row.likes_received,
            "reports_received": row.reports_received,
            "score": score,
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:limit]
