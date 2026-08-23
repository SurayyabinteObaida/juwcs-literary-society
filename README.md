# The Literary Society — Web App

A Flask + Jinja monolith for a university literary society: genre
communities, member-authored posts with editorial review, personal literary
profiles, per-user site themes, comments, likes/reports, automatic behavior
badges, a top-contributors leaderboard, and a versioned constitution page.

## Stack
- Flask 3 + Jinja templates (server-rendered, no separate frontend build)
- SQLAlchemy + Flask-Migrate (Alembic)
- Flask-Login for auth, Flask-WTF for forms/CSRF
- PostgreSQL in production (Neon), SQLite fallback for local dev
- Gunicorn for production serving

## How it works

- **Signup is open, not gated.** Anyone can register and is logged in
  immediately — there is no admin/editor approval step for creating an
  account. See `app/blueprints/auth`.
- **Three roles**: `user` (default), `editor`, `admin` — see
  `UserRole` in `app/models.py` and the guard decorators in `app/utils.py`
  (`admin_required`, `editor_required`, `roles_required`). Enforcement is on
  the backend (`403` on unauthorized routes), not just hidden UI.
- **Content goes through editorial review.** A member's poetry, shayari,
  blog, article, or review is created with `review_status = pending` and is
  only public once an Editor approves it (`app/blueprints/editor`). Editors
  can reject with feedback; the author can revise and resubmit
  (`app/blueprints/posts: edit`). Drafts are also supported.
- **Personal profiles** live at `/profile/u/<username>` (public) and
  `/profile/me` (your own, with full status breakdown: Published / Pending /
  Revision Required / Drafts). Edit at `/profile/edit`.
- **Per-user themes**: 6 palettes (Classic Light, Midnight/Dark, Royal,
  Paper & Ink, Literary Teal, Classic Sepia) implemented as CSS variables in
  `app/static/css/style.css`, switched via a `data-theme` attribute on
  `<html>`. Selection is saved on the `User` model and applied everywhere
  (`/profile/theme`, plus a quick-switch dropdown in the footer).
- **Admin** (`/admin`) manages editor promotion/demotion, can disable/
  re-enable accounts, browse all content by status, and moderate reports.
  Admins do not need to personally review every submission — that's the
  Editor's job — but can intervene on anything.
- **Communities** are seeded genres (Poetry, Fiction, Urdu Adab, Creative
  Non-fiction, Sci-Fi & Fantasy, Reviews), each with its own guidelines text
  and a controlled tag list members choose from when posting.
- **Posts** are capped at 2000 characters (`config.py: POST_MAX_CHARS`),
  enforced both client-side (live counter) and server-side. Only
  `approved` + `published` posts are ever shown in the feed, communities, or
  leaderboard.
- **Badges** are automatic and rule-based, awarded once content is approved
  — no admin action needed. Rules live in `config.py: BADGE_RULES`. The
  engine is in `app/services/badges.py`.
- **Top Contributors** is a live query (`app/services/leaderboard.py`), not
  a stored table, and only counts approved/published work:
  `score = posts×3 + likes×1 − reports×2`.
- **Constitution** is stored in the DB (`site_constitution` table,
  versioned) and rendered from Markdown — see "Editing the constitution"
  below.


## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env if you want to point at a real Postgres DB;
# otherwise it falls back to a local SQLite file automatically

export FLASK_APP=wsgi.py
flask db upgrade
flask seed --admin-email you@juw.edu.pk --admin-password "ChooseAStrongOne1" \
           --editor-email editor@juw.edu.pk --editor-password "ChooseAStrongOne2"

flask run
```

Visit `http://127.0.0.1:5000`. Anyone can register from `/auth/register` and
is logged in right away. Log in with the admin account you just seeded to
manage editors and moderate reports at `/admin`, or the editor account to
review submissions at `/editor`. The `--editor-*` flags are optional — you
can also promote any existing user to Editor later from `/admin/users`.

## Deploying to Render + Neon

1. **Create the Neon database** (if you haven't already) and copy its
   connection string — it looks like
   `postgresql://user:password@host/dbname?sslmode=require`.
2. **Push this repo to GitHub.**
3. **On Render**: New → Web Service → connect the repo. Render will pick up
   `render.yaml` automatically (Blueprint), or configure manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `flask db upgrade && flask seed && gunicorn wsgi:app`
   - Environment variables:
     - `DATABASE_URL` → your Neon connection string
     - `SECRET_KEY` → Render can auto-generate this (already set in
       `render.yaml`)
     - `FLASK_APP` → `wsgi.py`
     - `ADMIN_EMAIL` → the email you want to log in with
     - `ADMIN_PASSWORD` → a strong password for that account
4. **That's it** — the start command runs migrations, then `flask seed`
   (which reads `ADMIN_EMAIL`/`ADMIN_PASSWORD` automatically), then starts
   gunicorn. No manual shell step is required, and it's safe on every future
   deploy too: seeding starter communities/categories/badges is idempotent,
   and the admin block only creates the account if it doesn't already
   exist — if it does, it's just re-confirmed as `admin`/`approved` without
   touching the stored password. Promote any other user to Editor from
   `/admin/users`, or set `EDITOR_EMAIL`/`EDITOR_PASSWORD` the same way.

   Forgot to set `ADMIN_EMAIL`/`ADMIN_PASSWORD` before the first deploy?
   The app still starts — `flask seed` logs a warning and skips just the
   admin step instead of crashing the boot. Set both vars in the Render
   dashboard and redeploy (or trigger a manual redeploy) once ready.

## Editing the constitution later

The constitution is a DB row, not a template, so you can update it without
touching code. Easiest path for now: open a Python shell in the Render
environment (or locally against the prod `DATABASE_URL`) and add a new
version:

```python
from app import create_app
from app.extensions import db
from app.models import SiteConstitution

app = create_app()
with app.app_context():
    latest = SiteConstitution.query.order_by(SiteConstitution.version.desc()).first()
    db.session.add(SiteConstitution(version=latest.version + 1, body="""
# Your updated constitution text (Markdown)
...
"""))
    db.session.commit()
```

If this becomes something you want to do often, the natural next step is a
small admin form for it — flag it if you want that added.

## Events, Weekly Highlights, and the new "Editorial Ivory" landing page

This adds three things on top of the original app, without touching any
existing routes, models, or data:

- **Events** (`app/blueprints/events`, plus `app/blueprints/editor/events.py`)
  — Editors/Admins create and publish events (`/editor/events`), members
  register (`/events/<slug>`), duplicate registrations are blocked at the DB
  level (`UniqueConstraint(event_id, user_id)`), capacity/deadline are
  enforced server-side, and there's a confirmation screen with a
  downloadable `.ics` calendar file. Editors see a live registration list
  with name/username/email per event (`/editor/events/<id>/registrations`)
  — never exposed publicly.
- **Weekly Highlights + Gallery** (`app/blueprints/editor/highlights.py`,
  public routes on `main`) — Editors upload an image, title, description,
  category and contributor from `/editor/highlights`, with drag-and-drop +
  preview. The most recent published highlight appears on the landing page;
  all of them live in a masonry gallery at `/highlights`.
- **New models**: `Event`, `EventRegistration`, `WeeklyHighlight` — added via
  a real Alembic migration (`migrations/versions/..._add_events_...py`), not
  a schema reset. Run `flask db upgrade` as usual; your existing data is
  untouched.
- **New theme**: "Editorial Ivory" was added to the existing 6-palette theme
  system (no new mechanism — it's just a 7th entry in `THEME_CHOICES`). The
  public landing page always renders in Editorial Ivory regardless of a
  visitor's saved theme, per the brief; every other page still respects
  whatever palette a logged-in user has picked.
- **Redesigned navbar/footer** (`app/templates/base.html`) and a full
  landing-page rebuild (`app/templates/main/landing.html`) in the reference
  image's style — all data on it (community count, member count, published
  pieces, events, the featured event, the weekly highlight, the featured
  post) is queried live, nothing is hardcoded.

### ⚠️ Important: image uploads and Render's ephemeral disk

Event cover images and Weekly Highlight images are saved to
`app/static/uploads/` on local disk (validated for real file type, size,
and given random filenames — see `app/utils.py: save_uploaded_image`).
This works perfectly for local development and for any host with a
persistent disk. **On Render's free/standard web service tier, the
filesystem is ephemeral** — uploaded images will be wiped on every deploy
or dyno restart, exactly like the reason avatar uploads were originally
skipped in this project (see "out of scope" section below). Options if you
deploy this to Render:
- Add a [Render Disk](https://render.com/docs/disks) (persistent volume)
  mounted at `app/static/uploads`, or
- Swap `save_uploaded_image` for an S3/Cloudinary upload (same validation
  logic, different `.save()` call) before going live.
Locally, or on any host with a normal persistent disk, no changes are
needed.



- Avatar file uploads — profiles take an external image URL instead, to
  keep things simple on Render's ephemeral filesystem. Swap in S3/Cloudinary
  later if you want native uploads.
- Nested comment threads — comments are flat by design.
- Free-text tags — categories are a controlled list per community, editable
  by directly updating the `community_categories` table (or ask for a small
  admin UI for this once you know which tags communities actually want).

## Project layout

```
app/
  blueprints/       # auth, communities, posts, editor, profile, admin, main, bethak
  services/         # badges.py, leaderboard.py, seed.py
  templates/
  static/css/       # style.css — theme variable system (6 palettes)
  static/img/       # favicon.svg
  models.py
  extensions.py
  utils.py          # admin_required / editor_required / roles_required / approved_required
config.py            # POST_MAX_CHARS, BADGE_RULES live here
wsgi.py               # gunicorn entry point
render.yaml
```
