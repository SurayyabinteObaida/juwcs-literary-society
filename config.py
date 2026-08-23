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

    # Editorial image uploads (event covers, weekly highlight images)
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    ALLOWED_IMAGE_MIMETYPES = {"image/jpeg", "image/png", "image/webp"}
    MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # hard request cap (safety net)

    # Post / comment limits
    POST_MAX_CHARS = 2000
    COMMENT_MAX_CHARS = 500

    # Firebase Cloud Messaging — server credentials (Firebase Admin SDK) and
    # the public VAPID key handed to the browser for FCM registration.
    # See docs/FCM_NOTIFICATIONS.md for how to obtain/configure these.
    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID")
    FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL")
    FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY")
    FIREBASE_VAPID_PUBLIC_KEY = os.environ.get(
        "FIREBASE_VAPID_PUBLIC_KEY",
        "BCMVHss8Ms_9LLCwHRjilVQP8C9zQLq8lj-wkCNK4omfUMdtRgBzApoLYStAxzQuCI6sNxZuGaJT7Vo7t_NSHoM",
    )

    # Web app config is not a secret (it's shipped to every browser) but is
    # kept configurable via env vars so a fork can point at its own project
    # without editing source.
    FIREBASE_WEB_CONFIG = {
        "apiKey": os.environ.get("FIREBASE_API_KEY", "AIzaSyAlUvVmHvTWfYJlz_S2k7vtV8YiL6sCk-U"),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", "juw-literary-society.firebaseapp.com"),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID_WEB", "juw-literary-society"),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", "juw-literary-society.firebasestorage.app"),
        "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "703301282139"),
        "appId": os.environ.get("FIREBASE_APP_ID", "1:703301282139:web:b17eb27d17632a4831527e"),
        "measurementId": os.environ.get("FIREBASE_MEASUREMENT_ID", "G-2YWW0LWTFR"),
    }

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
