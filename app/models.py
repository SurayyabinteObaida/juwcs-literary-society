from datetime import datetime, timezone
from enum import Enum

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class UserStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserRole(str, Enum):
    MEMBER = "member"
    ADMIN = "admin"


class ReactionType(str, Enum):
    LIKE = "like"
    REPORT = "report"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False, default=UserRole.MEMBER.value)
    status = db.Column(db.String(20), nullable=False, default=UserStatus.PENDING.value)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    posts = db.relationship("Post", back_populates="author", lazy="dynamic")
    comments = db.relationship("Comment", back_populates="author", lazy="dynamic")
    reactions = db.relationship("Reaction", back_populates="user", lazy="dynamic")
    badges = db.relationship("UserBadge", back_populates="user", lazy="dynamic")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN.value

    @property
    def is_approved(self):
        return self.status == UserStatus.APPROVED.value

    def get_id(self):
        # Flask-Login calls this; keep default (str(self.id)) behavior explicit
        return str(self.id)

    def __repr__(self):
        return f"<User {self.email}>"


class Community(db.Model):
    __tablename__ = "communities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    guidelines_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    categories = db.relationship(
        "CommunityCategory", back_populates="community",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="CommunityCategory.label",
    )
    posts = db.relationship("Post", back_populates="community", lazy="dynamic")

    def __repr__(self):
        return f"<Community {self.slug}>"


class CommunityCategory(db.Model):
    __tablename__ = "community_categories"

    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    label = db.Column(db.String(80), nullable=False)

    community = db.relationship("Community", back_populates="categories")

    __table_args__ = (
        db.UniqueConstraint("community_id", "label", name="uq_category_per_community"),
    )


post_categories = db.Table(
    "post_categories",
    db.Column("post_id", db.Integer, db.ForeignKey("posts.id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("community_categories.id"), primary_key=True),
)


class PostStatus(str, Enum):
    PUBLISHED = "published"
    REMOVED = "removed"


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=PostStatus.PUBLISHED.value)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    community = db.relationship("Community", back_populates="posts")
    author = db.relationship("User", back_populates="posts")
    categories = db.relationship("CommunityCategory", secondary=post_categories, lazy="selectin")
    comments = db.relationship(
        "Comment", back_populates="post",
        cascade="all, delete-orphan", lazy="dynamic",
        order_by="Comment.created_at",
    )
    reactions = db.relationship(
        "Reaction", back_populates="post",
        cascade="all, delete-orphan", lazy="dynamic",
    )

    def reaction_count(self, reaction_type):
        return self.reactions.filter_by(type=reaction_type).count()

    def __repr__(self):
        return f"<Post {self.id} {self.title!r}>"


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    post = db.relationship("Post", back_populates="comments")
    author = db.relationship("User", back_populates="comments")


class Reaction(db.Model):
    __tablename__ = "reactions"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # like / report
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    post = db.relationship("Post", back_populates="reactions")
    user = db.relationship("User", back_populates="reactions")

    __table_args__ = (
        db.UniqueConstraint("post_id", "user_id", "type", name="uq_one_reaction_per_user_per_type"),
    )


class Badge(db.Model):
    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)  # matches config.BADGE_RULES key
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # positive / negative

    user_badges = db.relationship("UserBadge", back_populates="badge", lazy="dynamic")


class UserBadge(db.Model):
    __tablename__ = "user_badges"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False)
    awarded_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    source_post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)

    user = db.relationship("User", back_populates="badges")
    badge = db.relationship("Badge", back_populates="user_badges")

    __table_args__ = (
        db.UniqueConstraint("user_id", "badge_id", name="uq_badge_once_per_user"),
    )


class SiteConstitution(db.Model):
    __tablename__ = "site_constitution"

    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False)
    published_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class BethakStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class BethakSession(db.Model):
    """A single digital bethak thread — students volley shers/lines back and forth."""
    __tablename__ = "bethak_sessions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    topic = db.Column(db.String(160), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default=BethakStatus.OPEN.value)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    created_by = db.relationship("User")
    entries = db.relationship(
        "BethakEntry", back_populates="session",
        cascade="all, delete-orphan", lazy="dynamic",
        order_by="BethakEntry.created_at",
    )

    @property
    def is_open(self):
        return self.status == BethakStatus.OPEN.value

    def __repr__(self):
        return f"<BethakSession {self.id} {self.title!r}>"


class BethakEntry(db.Model):
    """One line/sher posted into a bethak session."""
    __tablename__ = "bethak_entries"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("bethak_sessions.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text = db.Column(db.String(400), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    session = db.relationship("BethakSession", back_populates="entries")
    author = db.relationship("User")
    reactions = db.relationship(
        "BethakReaction", back_populates="entry",
        cascade="all, delete-orphan", lazy="dynamic",
    )

    def reaction_count(self, reaction_type):
        return self.reactions.filter_by(type=reaction_type).count()


class BethakReaction(db.Model):
    __tablename__ = "bethak_reactions"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("bethak_entries.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # like / report
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    entry = db.relationship("BethakEntry", back_populates="reactions")
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("entry_id", "user_id", "type", name="uq_one_bethak_reaction_per_user_per_type"),
    )
