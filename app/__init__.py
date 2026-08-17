from flask import Flask, render_template
from flask_login import current_user

from config import Config
from app.extensions import db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    import markdown as _markdown

    from flask_wtf.csrf import generate_csrf
    app.jinja_env.globals["csrf_token"] = generate_csrf

    @app.template_filter("markdown")
    def markdown_filter(text):
        if not text:
            return ""
        return _markdown.markdown(text, extensions=["extra"])

    @app.template_filter("excerpt")
    def excerpt_filter(text, length=220):
        if not text:
            return ""
        text = " ".join(text.split())
        if len(text) <= length:
            return text
        return text[:length].rsplit(" ", 1)[0] + "\u2026"

    @app.template_filter("stock_photo")
    def stock_photo_filter(seed, width=800, height=600):
        # Deterministic placeholder photography (Picsum Photos — free to hotlink,
        # no attribution required, no API key). Swap for real Society photography
        # whenever it's available; every <img> using this filter just needs a new src.
        import hashlib
        digest = hashlib.md5(str(seed).encode("utf-8")).hexdigest()[:10]
        return f"https://picsum.photos/seed/juwcs-{digest}/{width}/{height}"

    from app.blueprints.main import bp as main_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.communities import bp as communities_bp
    from app.blueprints.posts import bp as posts_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.editor import bp as editor_bp
    from app.blueprints.profile import bp as profile_bp
    from app.blueprints.bethak import bp as bethak_bp
    from app.blueprints.events import bp as events_bp
    from app.blueprints.notifications import bp as notifications_bp
    from app.blueprints.media import bp as media_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(communities_bp, url_prefix="/communities")
    app.register_blueprint(posts_bp, url_prefix="/posts")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(editor_bp, url_prefix="/editor")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(bethak_bp, url_prefix="/bethak")
    app.register_blueprint(events_bp, url_prefix="/events")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")
    app.register_blueprint(media_bp)

    # Images are stored in the database now (see app.models.StoredImage), so
    # the filesystem upload folder is no longer required at runtime. It's
    # only still referenced by scripts/migrate_legacy_images.py, which reads
    # any pre-existing files from here on demand — no need to create it eagerly.

    from app.models import THEME_CHOICES, DEFAULT_THEME

    @app.context_processor
    def inject_globals():
        unread_notifications = 0
        if getattr(current_user, "is_authenticated", False):
            from app.models import Notification
            unread_notifications = Notification.query.filter_by(
                user_id=current_user.id, is_read=False,
            ).count()
        return {
            "THEME_CHOICES": THEME_CHOICES,
            "DEFAULT_THEME": DEFAULT_THEME,
            "unread_notifications_count": unread_notifications,
            "FIREBASE_VAPID_PUBLIC_KEY": app.config["FIREBASE_VAPID_PUBLIC_KEY"],
        }

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.route("/firebase-messaging-sw.js")
    def firebase_messaging_sw():
        # Served from the domain root (not /static/) so the service worker's
        # scope covers the whole site — required for FCM background push +
        # notification-click handling to reach every page, not just /static/.
        from flask import send_from_directory
        response = send_from_directory(
            app.static_folder, "firebase-messaging-sw.js", mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    register_cli(app)

    return app


def register_cli(app):
    import click

    @app.cli.command("notify-event-reminders")
    def notify_event_reminders():
        """Send the 24h/1h event-reminder pushes to registered attendees.

        Idempotent — safe to run repeatedly (NotificationDedupe guarantees
        at-most-once per event/user/window), so this is meant to be invoked
        periodically (every 15-30 minutes) by an external scheduler such as
        a Render Cron Job — see docs/FCM_NOTIFICATIONS.md. Deliberately NOT
        run in-process inside the web dyno/Gunicorn workers, which would
        either miss ticks or (worse) fire duplicate sends across workers.
        """
        from datetime import datetime, timezone, timedelta
        from app.models import Event, EventStatus
        from app.services.notification_service import notify_event_reminder

        now = datetime.now(timezone.utc)

        due_24h = Event.query.filter(
            Event.status == EventStatus.PUBLISHED.value,
            Event.start_at > now + timedelta(hours=1),
            Event.start_at <= now + timedelta(hours=24),
        ).all()
        due_1h = Event.query.filter(
            Event.status == EventStatus.PUBLISHED.value,
            Event.start_at > now,
            Event.start_at <= now + timedelta(hours=1),
        ).all()

        # notify_event_reminder() builds links with url_for(), which needs a
        # request context to know the site's URL scheme/host — CLI commands
        # don't have one by default.
        with app.test_request_context():
            sent_24h = sum(len(notify_event_reminder(e, 24)) for e in due_24h)
            sent_1h = sum(len(notify_event_reminder(e, 1)) for e in due_1h)

        click.echo(f"24h reminders sent: {sent_24h} | 1h reminders sent: {sent_1h}")

    @app.cli.command("seed")
    @click.option("--admin-email", default=None, help="Create/promote an admin with this email.")
    @click.option("--admin-password", default=None, help="Password for the admin account (required if creating).")
    @click.option("--editor-email", default=None, help="Create/promote an editor with this email.")
    @click.option("--editor-password", default=None, help="Password for the editor account (required if creating).")
    def seed(admin_email, admin_password, editor_email, editor_password):
        """Seed starter communities, categories, badge catalog, and (optionally) an admin/editor user."""
        from app.services.seed import run_seed
        run_seed(
            admin_email=admin_email, admin_password=admin_password,
            editor_email=editor_email, editor_password=editor_password,
        )
        click.echo("Seed complete.")
