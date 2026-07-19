from flask import Flask, render_template

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

    from app.blueprints.main import bp as main_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.communities import bp as communities_bp
    from app.blueprints.posts import bp as posts_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.bethak import bp as bethak_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(communities_bp, url_prefix="/communities")
    app.register_blueprint(posts_bp, url_prefix="/posts")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(bethak_bp, url_prefix="/bethak")

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    register_cli(app)

    return app


def register_cli(app):
    import click

    @app.cli.command("seed")
    @click.option("--admin-email", default=None, help="Create/promote an admin with this email.")
    @click.option("--admin-password", default=None, help="Password for the admin account (required if creating).")
    def seed(admin_email, admin_password):
        """Seed starter communities, categories, badge catalog, and (optionally) an admin user."""
        from app.services.seed import run_seed
        run_seed(admin_email=admin_email, admin_password=admin_password)
        click.echo("Seed complete.")
