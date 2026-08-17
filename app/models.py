from datetime import datetime, timezone
from enum import Enum

from flask import url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


def as_aware_utc(dt):
    """Coerce a naive datetime to UTC-aware so it can be safely compared
    against utcnow(). Some rows were written before timezone-aware storage
    was consistently enforced at the form layer — this keeps reads safe
    regardless of how the value was originally saved."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class UserStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserRole(str, Enum):
    """Three-tier role system.

    USER   — normal registered member; signs up/logs in freely, submits content.
    EDITOR — reviews/approves/rejects user-submitted content before it goes public.
    ADMIN  — full system control; manages editors, roles, and platform settings.
    """
    USER = "user"
    EDITOR = "editor"
    ADMIN = "admin"


THEME_CHOICES = [
    ("classic-literary", "Classic Literary"),
    ("literary-green", "Literary Green"),
    ("royal-blue", "Royal Blue"),
    ("rose-poetry", "Rose Poetry"),
    ("midnight", "Midnight"),
]
DEFAULT_THEME = "classic-literary"
VALID_THEMES = {code for code, _ in THEME_CHOICES}

# Legacy theme slugs (pre theme-system-v2) mapped onto the five current themes,
# so existing user records and cookies keep resolving to a sensible theme.
LEGACY_THEME_ALIASES = {
    "classic-light": "classic-literary",
    "paper-ink": "classic-literary",
    "classic-sepia": "classic-literary",
    "literary-teal": "literary-green",
    "editorial-ivory": "literary-green",
    "royal": "royal-blue",
    "midnight-dark": "midnight",
}


class ContentType(str, Enum):
    POETRY = "poetry"
    SHAYARI = "shayari"
    BLOG = "blog"
    ARTICLE = "article"
    REVIEW = "review"
    OTHER = "other"


CONTENT_TYPE_LABELS = {
    ContentType.POETRY.value: "Poetry",
    ContentType.SHAYARI.value: "Shayari",
    ContentType.BLOG.value: "Blog",
    ContentType.ARTICLE.value: "Article",
    ContentType.REVIEW.value: "Review",
    ContentType.OTHER.value: "Other",
}


class ReviewStatus(str, Enum):
    """Editorial workflow status for a single piece of user-submitted content."""
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReactionType(str, Enum):
    LIKE = "like"
    REPORT = "report"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(60), unique=True, nullable=True, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False, default=UserRole.USER.value)
    status = db.Column(db.String(20), nullable=False, default=UserStatus.APPROVED.value)

    # Literary profile
    bio = db.Column(db.String(500), nullable=True)
    interests = db.Column(db.String(300), nullable=True)  # comma-separated favorite genres/interests
    avatar_url = db.Column(db.String(500), nullable=True)

    # Personalization
    theme = db.Column(db.String(30), nullable=False, default=DEFAULT_THEME)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    posts = db.relationship("Post", back_populates="author", lazy="dynamic",
                             foreign_keys="Post.author_id")
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
    def is_editor(self):
        return self.role == UserRole.EDITOR.value

    @property
    def is_editor_or_admin(self):
        return self.role in (UserRole.EDITOR.value, UserRole.ADMIN.value)

    @property
    def role_label(self):
        return {
            UserRole.ADMIN.value: "Admin",
            UserRole.EDITOR.value: "Editor",
            UserRole.USER.value: "Member",
        }.get(self.role, "Member")

    @property
    def is_approved(self):
        return self.status == UserStatus.APPROVED.value

    @property
    def display_theme(self):
        if self.theme in VALID_THEMES:
            return self.theme
        return LEGACY_THEME_ALIASES.get(self.theme, DEFAULT_THEME)

    @property
    def interest_list(self):
        if not self.interests:
            return []
        return [i.strip() for i in self.interests.split(",") if i.strip()]

    @property
    def approved_post_count(self):
        return self.posts.filter_by(review_status=ReviewStatus.APPROVED.value).count()

    @property
    def pending_post_count(self):
        return self.posts.filter_by(review_status=ReviewStatus.PENDING.value).count()

    @property
    def rejected_post_count(self):
        return self.posts.filter_by(review_status=ReviewStatus.REJECTED.value).count()

    @property
    def likes_received(self):
        post_ids = [p.id for p in self.posts]
        if not post_ids:
            return 0
        return Reaction.query.filter(
            Reaction.type == ReactionType.LIKE.value, Reaction.post_id.in_(post_ids)
        ).count()

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
    content_type = db.Column(db.String(20), nullable=False, default=ContentType.OTHER.value)

    # `status` = post visibility after publication (published / removed by admin).
    status = db.Column(db.String(20), nullable=False, default=PostStatus.PUBLISHED.value)

    # `review_status` = editorial workflow (draft -> pending -> approved/rejected).
    review_status = db.Column(db.String(20), nullable=False, default=ReviewStatus.PENDING.value)
    rejection_reason = db.Column(db.String(600), nullable=True)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    community = db.relationship("Community", back_populates="posts")
    author = db.relationship("User", back_populates="posts", foreign_keys=[author_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
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

    @property
    def is_public(self):
        """Only approved + published content is visible to the general audience."""
        return (
            self.review_status == ReviewStatus.APPROVED.value
            and self.status == PostStatus.PUBLISHED.value
        )

    @property
    def content_type_label(self):
        return CONTENT_TYPE_LABELS.get(self.content_type, "Writing")

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


# =============================================================================
# Image storage (PostgreSQL-backed — replaces filesystem uploads)
# =============================================================================

class StoredImage(db.Model):
    """An uploaded image, persisted as binary data inside the database.

    Render's free-tier filesystem is ephemeral (wiped on every deploy/restart),
    so anything written to app/static/uploads would eventually disappear.
    Storing the bytes here means images live in the same Postgres database as
    everything else and survive deploys/restarts.
    """
    __tablename__ = "stored_images"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    # Deferred: the raw bytes are only fetched from Postgres when something
    # actually reads `.data` (i.e. the /media/image/<id> route below). Every
    # other place that touches a StoredImage — event/highlight listings,
    # detail pages building a `.url`, admin dashboards — loads the row
    # without pulling the binary payload along with it.
    data = db.deferred(db.Column(db.LargeBinary, nullable=False))
    size_bytes = db.Column(db.Integer, nullable=True)

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    uploaded_by = db.relationship("User")

    @property
    def url(self):
        return url_for("media.image", image_id=self.id)

    def __repr__(self):
        return f"<StoredImage {self.id} {self.filename!r} {self.mimetype}>"


# =============================================================================
# Events + Registrations
# =============================================================================

class EventStatus(str, Enum):
    DRAFT = "draft"          # editor is still working on it — not publicly visible
    PUBLISHED = "published"  # visible on the public site
    CANCELLED = "cancelled"  # kept for history, shown as cancelled


class EventCategory(str, Enum):
    POETRY = "poetry"
    OPEN_MIC = "open_mic"
    WORKSHOP = "workshop"
    DISCUSSION = "discussion"
    BOOK_CLUB = "book_club"
    BETHAK = "bethak"
    OTHER = "other"


EVENT_CATEGORY_LABELS = {
    EventCategory.POETRY.value: "Poetry",
    EventCategory.OPEN_MIC.value: "Open Mic",
    EventCategory.WORKSHOP.value: "Workshop",
    EventCategory.DISCUSSION.value: "Literary Discussion",
    EventCategory.BOOK_CLUB.value: "Book Club",
    EventCategory.BETHAK.value: "Bethak",
    EventCategory.OTHER.value: "Society Event",
}


class RegistrationStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


def _slugify(value):
    import re
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), nullable=False, default=EventCategory.OTHER.value)

    # Legacy filesystem path (pre-Postgres-image-storage). No longer written
    # to by the app; kept only so `scripts/migrate_legacy_images.py` has
    # something to read when importing old app/static/uploads files.
    legacy_cover_image_path = db.Column("cover_image", db.String(300), nullable=True)

    cover_image_id = db.Column(db.Integer, db.ForeignKey("stored_images.id"), nullable=True)
    cover_image = db.relationship("StoredImage", foreign_keys=[cover_image_id])

    venue = db.Column(db.String(200), nullable=False)
    organizer = db.Column(db.String(160), nullable=True)

    start_at = db.Column(db.DateTime(timezone=True), nullable=False)
    end_at = db.Column(db.DateTime(timezone=True), nullable=True)
    registration_deadline = db.Column(db.DateTime(timezone=True), nullable=True)

    capacity = db.Column(db.Integer, nullable=True)  # null = unlimited

    status = db.Column(db.String(20), nullable=False, default=EventStatus.DRAFT.value)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    created_by = db.relationship("User")
    registrations = db.relationship(
        "EventRegistration", back_populates="event",
        cascade="all, delete-orphan", lazy="dynamic",
    )

    @staticmethod
    def make_unique_slug(title):
        base = _slugify(title)
        slug = base
        n = 2
        while Event.query.filter_by(slug=slug).first() is not None:
            slug = f"{base}-{n}"
            n += 1
        return slug

    @property
    def category_label(self):
        return EVENT_CATEGORY_LABELS.get(self.category, "Society Event")

    @property
    def is_published(self):
        return self.status == EventStatus.PUBLISHED.value

    @property
    def is_cancelled(self):
        return self.status == EventStatus.CANCELLED.value

    @property
    def confirmed_registration_count(self):
        return self.registrations.filter_by(status=RegistrationStatus.CONFIRMED.value).count()

    @property
    def seats_remaining(self):
        if self.capacity is None:
            return None
        return max(self.capacity - self.confirmed_registration_count, 0)

    @property
    def is_full(self):
        return self.capacity is not None and self.seats_remaining <= 0

    @property
    def registration_closed(self):
        deadline = as_aware_utc(self.registration_deadline)
        if deadline and utcnow() > deadline:
            return True
        end = as_aware_utc(self.end_at)
        if end and utcnow() > end:
            return True
        return False

    @property
    def can_register(self):
        return self.is_published and not self.is_cancelled and not self.is_full and not self.registration_closed

    def registration_for(self, user):
        if not user or not user.is_authenticated:
            return None
        return self.registrations.filter_by(
            user_id=user.id, status=RegistrationStatus.CONFIRMED.value,
        ).first()

    def __repr__(self):
        return f"<Event {self.id} {self.title!r}>"


class EventRegistration(db.Model):
    __tablename__ = "event_registrations"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    reference = db.Column(db.String(20), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=RegistrationStatus.CONFIRMED.value)
    registered_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    event = db.relationship("Event", back_populates="registrations")
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("event_id", "user_id", name="uq_one_registration_per_user_per_event"),
    )

    @staticmethod
    def make_reference():
        import secrets
        return "JLS-" + secrets.token_hex(3).upper()

    def __repr__(self):
        return f"<EventRegistration {self.reference}>"


# =============================================================================
# Weekly Highlights / Gallery
# =============================================================================

class HighlightCategory(str, Enum):
    POETRY = "poetry"
    FICTION = "fiction"
    NONFICTION = "nonfiction"
    REVIEW = "review"
    URDU_ADAB = "urdu_adab"
    EVENT_RECAP = "event_recap"
    OTHER = "other"


HIGHLIGHT_CATEGORY_LABELS = {
    HighlightCategory.POETRY.value: "Poetry",
    HighlightCategory.FICTION.value: "Fiction",
    HighlightCategory.NONFICTION.value: "Creative Non-fiction",
    HighlightCategory.REVIEW.value: "Book Review",
    HighlightCategory.URDU_ADAB.value: "Urdu Adab",
    HighlightCategory.EVENT_RECAP.value: "Event Recap",
    HighlightCategory.OTHER.value: "Editor's Pick",
}


class WeeklyHighlight(db.Model):
    __tablename__ = "weekly_highlights"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    editorial_note = db.Column(db.Text, nullable=True)

    # Legacy filesystem path (pre-Postgres-image-storage). No longer written
    # to by the app; kept only so `scripts/migrate_legacy_images.py` has
    # something to read when importing old app/static/uploads files.
    legacy_image_path = db.Column("image_path", db.String(300), nullable=True)

    image_id = db.Column(db.Integer, db.ForeignKey("stored_images.id"), nullable=True)
    image = db.relationship("StoredImage", foreign_keys=[image_id])

    category = db.Column(db.String(30), nullable=False, default=HighlightCategory.OTHER.value)

    contributor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    contributor_name = db.Column(db.String(160), nullable=True)  # fallback if no linked user

    related_post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)

    published = db.Column(db.Boolean, default=False, nullable=False)
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    contributor = db.relationship("User", foreign_keys=[contributor_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    related_post = db.relationship("Post")

    @staticmethod
    def make_unique_slug(title):
        base = _slugify(title)
        slug = base
        n = 2
        while WeeklyHighlight.query.filter_by(slug=slug).first() is not None:
            slug = f"{base}-{n}"
            n += 1
        return slug

    @property
    def category_label(self):
        return HIGHLIGHT_CATEGORY_LABELS.get(self.category, "Editor's Pick")

    @property
    def display_contributor(self):
        if self.contributor:
            return self.contributor.name
        return self.contributor_name or "The Editorial Desk"

    def __repr__(self):
        return f"<WeeklyHighlight {self.id} {self.title!r}>"


# =============================================================================
# Firebase Cloud Messaging — push subscriptions, in-app notifications
# =============================================================================

class NotificationType(str, Enum):
    EVENT_CREATED = "event_created"
    EVENT_REGISTRATION = "event_registration"
    EVENT_REMINDER = "event_reminder"
    EVENT_STARTING = "event_starting"
    BETHAK_OPENED = "bethak_opened"
    POST_APPROVED = "post_approved"
    POST_REJECTED = "post_rejected"
    POST_CHANGES_REQUESTED = "post_changes_requested"
    EDITOR_PICK = "editor_pick"
    NEW_PUBLICATION = "new_publication"
    ANNOUNCEMENT = "announcement"
    COMMENT = "comment"
    REPLY = "reply"
    SYSTEM = "system"


# Maps each notification type onto the NotificationPreference column that
# gates it. Types not listed here (e.g. private submission-status updates)
# are always delivered and can't be turned off.
NOTIFICATION_PREFERENCE_MAP = {
    NotificationType.EVENT_CREATED.value: "events_new",
    NotificationType.EVENT_REMINDER.value: "events_reminders",
    NotificationType.EVENT_STARTING.value: "events_reminders",
    NotificationType.BETHAK_OPENED.value: "bethak_opens",
    NotificationType.NEW_PUBLICATION.value: "literary_new_publications",
    NotificationType.EDITOR_PICK.value: "literary_editors_picks",
    NotificationType.POST_APPROVED.value: "activity_submission_approved",
    NotificationType.POST_REJECTED.value: "activity_submission_rejected",
    NotificationType.POST_CHANGES_REQUESTED.value: "activity_changes_requested",
    NotificationType.COMMENT.value: "community_comments",
    NotificationType.REPLY.value: "community_comments",
    NotificationType.ANNOUNCEMENT.value: "system_announcements",
    NotificationType.SYSTEM.value: "system_announcements",
}


class NotificationPreference(db.Model):
    """One row per user. Every category defaults to enabled (opt-out model),
    matching the existing site's low-friction registration flow."""
    __tablename__ = "notification_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    events_new = db.Column(db.Boolean, nullable=False, default=True)
    events_reminders = db.Column(db.Boolean, nullable=False, default=True)
    bethak_opens = db.Column(db.Boolean, nullable=False, default=True)
    literary_new_publications = db.Column(db.Boolean, nullable=False, default=True)
    literary_editors_picks = db.Column(db.Boolean, nullable=False, default=True)
    activity_submission_approved = db.Column(db.Boolean, nullable=False, default=True)
    activity_submission_rejected = db.Column(db.Boolean, nullable=False, default=True)
    activity_changes_requested = db.Column(db.Boolean, nullable=False, default=True)
    community_comments = db.Column(db.Boolean, nullable=False, default=True)
    system_announcements = db.Column(db.Boolean, nullable=False, default=True)

    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User")

    def allows(self, notification_type):
        field = NOTIFICATION_PREFERENCE_MAP.get(notification_type)
        if field is None:
            return True  # private/system-critical types are never gated
        return bool(getattr(self, field, True))

    @staticmethod
    def get_or_create(user):
        pref = NotificationPreference.query.filter_by(user_id=user.id).first()
        if pref is None:
            pref = NotificationPreference(user_id=user.id)
            db.session.add(pref)
            db.session.flush()
        return pref


class PushSubscription(db.Model):
    """A single browser/device registered for FCM push, tied to a user.
    One user may have several (Chrome desktop, Edge desktop, mobile, ...)."""
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # The current FCM registration token for this browser installation.
    # Firebase may rotate this value over time — updates happen in place.
    fcm_token = db.Column(db.String(500), unique=True, nullable=False, index=True)

    browser = db.Column(db.String(60), nullable=True)
    device = db.Column(db.String(60), nullable=True)
    platform = db.Column(db.String(60), nullable=True)
    user_agent = db.Column(db.String(400), nullable=True)

    enabled = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_used_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User")

    def __repr__(self):
        return f"<PushSubscription user={self.user_id} {self.browser or '?'}>"


class Notification(db.Model):
    """In-app notification-center entry. Created alongside (and independently
    of) any push delivery, so the bell/center works even if FCM is down."""
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    type = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(300), nullable=True)

    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)
    bethak_session_id = db.Column(db.Integer, db.ForeignKey("bethak_sessions.id"), nullable=True)

    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    user = db.relationship("User")
    event = db.relationship("Event")
    post = db.relationship("Post")
    bethak_session = db.relationship("BethakSession")

    @property
    def icon(self):
        return {
            NotificationType.EVENT_CREATED.value: "📅",
            NotificationType.EVENT_REGISTRATION.value: "✅",
            NotificationType.EVENT_REMINDER.value: "📅",
            NotificationType.EVENT_STARTING.value: "⏰",
            NotificationType.BETHAK_OPENED.value: "🪶",
            NotificationType.POST_APPROVED.value: "✨",
            NotificationType.POST_REJECTED.value: "✎",
            NotificationType.POST_CHANGES_REQUESTED.value: "✏️",
            NotificationType.EDITOR_PICK.value: "✨",
            NotificationType.NEW_PUBLICATION.value: "📖",
            NotificationType.ANNOUNCEMENT.value: "📣",
            NotificationType.COMMENT.value: "💬",
            NotificationType.REPLY.value: "💬",
            NotificationType.SYSTEM.value: "🔔",
        }.get(self.type, "🔔")

    def __repr__(self):
        return f"<Notification {self.id} {self.type} user={self.user_id}>"


class NotificationDedupe(db.Model):
    """Idempotency guard for automatic notifications that must fire at most
    once per (kind, subject). Used for event reminders (24h/1h) and any
    other automatic trigger that could otherwise double-send — e.g. across
    concurrent Gunicorn workers or retried cron ticks."""
    __tablename__ = "notification_dedupes"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(60), nullable=False)  # e.g. "event_reminder_24h"
    subject_id = db.Column(db.String(120), nullable=False)  # e.g. "event:12:user:5"
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("kind", "subject_id", name="uq_notification_dedupe"),
    )
