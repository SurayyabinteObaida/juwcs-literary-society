from app.extensions import db
from app.models import Community, CommunityCategory, User, UserRole, UserStatus, SiteConstitution
from app.services.badges import sync_badge_catalog

STARTER_COMMUNITIES = [
    {
        "name": "Poetry",
        "slug": "poetry",
        "description": "Verse in any form or language.",
        "guidelines_text": "Share original poetry. Be generous with feedback, gentle with critique.",
        "categories": ["Ghazal", "Free Verse", "Sonnet", "Nazm", "Haiku"],
    },
    {
        "name": "Fiction",
        "slug": "fiction",
        "description": "Short stories and fiction in progress.",
        "guidelines_text": "Original fiction only. Excerpts from longer works are welcome — label them clearly.",
        "categories": ["Short Story", "Flash Fiction", "Micro-fiction", "Excerpt"],
    },
    {
        "name": "Urdu Adab",
        "slug": "urdu-adab",
        "description": "اردو ادب — Urdu literature and writing.",
        "guidelines_text": "اردو نظم، غزل، اور نثر کے لیے مخصوص جگہ۔",
        "categories": ["Nazm", "Ghazal", "Afsana", "Mazmoon"],
    },
    {
        "name": "Creative Non-fiction",
        "slug": "creative-nonfiction",
        "description": "Personal essays, reflections, and true stories, told well.",
        "guidelines_text": "Nonfiction means it happened — but tell it with craft.",
        "categories": ["Personal Essay", "Reflection", "Travel Writing"],
    },
    {
        "name": "Sci-Fi & Fantasy",
        "slug": "scifi-fantasy",
        "description": "Speculative fiction of all kinds.",
        "guidelines_text": "World-building, short stories, and flash fiction set anywhere but here.",
        "categories": ["Short Story", "World-building", "Flash Fiction"],
    },
    {
        "name": "Book & Film Reviews",
        "slug": "reviews",
        "description": "What you've been reading and watching.",
        "guidelines_text": "Reviews should be thoughtful, not just ratings. Spoiler warnings appreciated.",
        "categories": ["Book Review", "Film Review", "Recommendation"],
    },
]

DEFAULT_CONSTITUTION = """\
# Literary Society Constitution (v1)

## Purpose
This society exists to give students a space to write, share, and respond to \
each other's creative work — poetry, fiction, essays, and beyond — regardless \
of experience level.

## Membership
Membership is open to all students. Registration requests are reviewed and \
approved by the faculty head/admin before posting access is granted.

## Community Guidelines
1. Share original work only.
2. Critique the work, not the person.
3. No plagiarism — proper attribution is required for any quoted material.
4. Content should remain appropriate for a university community space.
5. Reports are reviewed by the admin; repeated violations may result in \
   restricted posting privileges.

## Amendments
This constitution may be revised by the faculty head. Revisions are versioned \
and the current version is always visible on the site.
"""


def run_seed(admin_email=None, admin_password=None):
    for c in STARTER_COMMUNITIES:
        community = Community.query.filter_by(slug=c["slug"]).first()
        if not community:
            community = Community(
                name=c["name"], slug=c["slug"],
                description=c["description"], guidelines_text=c["guidelines_text"],
            )
            db.session.add(community)
            db.session.flush()
        existing_labels = {cat.label for cat in community.categories}
        for label in c["categories"]:
            if label not in existing_labels:
                db.session.add(CommunityCategory(community_id=community.id, label=label))

    if not SiteConstitution.query.first():
        db.session.add(SiteConstitution(version=1, body=DEFAULT_CONSTITUTION))

    db.session.commit()

    sync_badge_catalog()

    if admin_email:
        user = User.query.filter_by(email=admin_email).first()
        if user:
            user.role = UserRole.ADMIN.value
            user.status = UserStatus.APPROVED.value
        else:
            if not admin_password:
                raise ValueError("admin_password is required when creating a new admin user")
            user = User(
                name="Society Admin", email=admin_email,
                role=UserRole.ADMIN.value, status=UserStatus.APPROVED.value,
            )
            user.set_password(admin_password)
            db.session.add(user)
        db.session.commit()
