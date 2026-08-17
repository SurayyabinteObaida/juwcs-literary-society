"""
Rule-based badge engine.

Badges are defined in config.BADGE_RULES (code -> rule dict) and mirrored
into the `badges` table by `sync_badge_catalog()` (called once at startup
or via `flask seed-badges`). Awarding happens synchronously right after the
event that could trigger it (new post, new like, new report) — cheap at
this scale, no background job needed.
"""
from flask import current_app

from app.extensions import db
from app.models import Badge, UserBadge, Reaction, ReactionType, Post, ReviewStatus, PostStatus


def sync_badge_catalog():
    """Ensure every badge in config exists as a row in the badges table."""
    rules = current_app.config["BADGE_RULES"]
    existing = {b.code: b for b in Badge.query.all()}

    for code, rule in rules.items():
        if code in existing:
            b = existing[code]
            b.label = rule["label"]
            b.description = rule["description"]
            b.kind = rule["kind"]
        else:
            db.session.add(Badge(
                code=code,
                label=rule["label"],
                description=rule["description"],
                kind=rule["kind"],
            ))
    db.session.commit()


def _award_if_missing(user, code, source_post_id=None):
    badge = Badge.query.filter_by(code=code).first()
    if not badge:
        return None
    already = UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first()
    if already:
        return None
    ub = UserBadge(user_id=user.id, badge_id=badge.id, source_post_id=source_post_id)
    db.session.add(ub)
    return ub


def _public_post_ids(user):
    return [
        p.id for p in user.posts.filter_by(
            review_status=ReviewStatus.APPROVED.value, status=PostStatus.PUBLISHED.value,
        )
    ]


def _metric_post_count(user):
    return user.posts.filter_by(
        review_status=ReviewStatus.APPROVED.value, status=PostStatus.PUBLISHED.value,
    ).count()


def _metric_likes_received(user):
    post_ids = _public_post_ids(user)
    if not post_ids:
        return 0
    return (
        Reaction.query
        .filter(Reaction.type == ReactionType.LIKE.value, Reaction.post_id.in_(post_ids))
        .count()
    )


def _metric_reports_received_total(user):
    post_ids = _public_post_ids(user)
    if not post_ids:
        return 0
    return (
        Reaction.query
        .filter(Reaction.type == ReactionType.REPORT.value, Reaction.post_id.in_(post_ids))
        .count()
    )


def _metric_reports_on_single_post(post):
    return post.reaction_count(ReactionType.REPORT.value)


def evaluate_user_badges(user, triggered_by_post=None):
    """
    Check all user-level (post_count / likes_received / reports_received_total)
    rules for this user, and the single-post rule for `triggered_by_post` if given.
    Awards any newly-earned badges. Commits at the end.
    """
    rules = current_app.config["BADGE_RULES"]
    newly_awarded = []

    post_count = None
    likes_received = None
    reports_total = None

    for code, rule in rules.items():
        metric = rule["metric"]
        threshold = rule["threshold"]

        if metric == "post_count":
            if post_count is None:
                post_count = _metric_post_count(user)
            value = post_count
        elif metric == "likes_received":
            if likes_received is None:
                likes_received = _metric_likes_received(user)
            value = likes_received
        elif metric == "reports_received_total":
            if reports_total is None:
                reports_total = _metric_reports_received_total(user)
            value = reports_total
        elif metric == "reports_on_single_post":
            if triggered_by_post is None:
                continue
            value = _metric_reports_on_single_post(triggered_by_post)
        else:
            continue

        if value >= threshold:
            ub = _award_if_missing(
                user, code,
                source_post_id=triggered_by_post.id if triggered_by_post else None,
            )
            if ub:
                newly_awarded.append(code)

    if newly_awarded:
        db.session.commit()
    return newly_awarded
