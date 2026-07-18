import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # Neon (and most managed Postgres) connection strings arrive as
    # postgres://... but SQLAlchemy 2.x / psycopg2 want postgresql://
    _raw_db_url = os.environ.get("DATABASE_URL", "")
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif _raw_db_url.startswith("postgresql://"):
        _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url or f"sqlite:///{os.path.join(basedir, 'dev.db')}"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,   # avoids stale-connection errors on serverless PG
        "pool_recycle": 300,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Post / comment limits
    POST_MAX_CHARS = 2000
    COMMENT_MAX_CHARS = 500

    # Badge thresholds (rule-based, automatic)
    BADGE_RULES = {
        "first_post": {"kind": "positive", "metric": "post_count", "threshold": 1,
                        "label": "First Post", "description": "Published their first post."},
        "prolific_writer": {"kind": "positive", "metric": "post_count", "threshold": 10,
                             "label": "Prolific Writer", "description": "Published 10 posts."},
        "well_liked": {"kind": "positive", "metric": "likes_received", "threshold": 10,
                        "label": "Well Liked", "description": "Received 10 likes across posts."},
        "community_favorite": {"kind": "positive", "metric": "likes_received", "threshold": 25,
                                "label": "Community Favorite", "description": "Received 25 likes across posts."},
        "flagged_content": {"kind": "negative", "metric": "reports_on_single_post", "threshold": 3,
                             "label": "Flagged Content", "description": "A post received 3+ reports."},
        "repeated_concern": {"kind": "negative", "metric": "reports_received_total", "threshold": 6,
                              "label": "Repeated Concern", "description": "Received 6+ reports across posts."},
    }
