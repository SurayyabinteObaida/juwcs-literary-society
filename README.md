# The Literary Society — Web App

A Flask + Jinja monolith for a university literary society: genre communities,
member-authored posts with self-tagged categories, comments, likes/reports,
automatic behavior badges, a top-contributors leaderboard, and a versioned
constitution/guidelines page.

## Stack
- Flask 3 + Jinja templates (server-rendered, no separate frontend build)
- SQLAlchemy + Flask-Migrate (Alembic)
- Flask-Login for auth, Flask-WTF for forms/CSRF
- PostgreSQL in production (Neon), SQLite fallback for local dev
- Gunicorn for production serving

## How it works

- **Signup is gated**: students register, an admin approves before they can
  post, comment, or react. There is no student "editor" role in this
  version — the admin (society head) manages everything directly.
- **Communities** are seeded genres (Poetry, Fiction, Urdu Adab, Creative
  Non-fiction, Sci-Fi & Fantasy, Reviews), each with its own guidelines text
  and a controlled tag list members choose from when posting.
- **Posts** are capped at 2000 characters (`config.py: POST_MAX_CHARS`),
  enforced both client-side (live counter) and server-side.
- **Badges** are automatic and rule-based — no admin action needed. Rules
  live in `config.py: BADGE_RULES` (e.g. first post, 10 posts, 10 likes
  received, 3+ reports on a single post, 6+ reports total). The engine is
  in `app/services/badges.py` and runs right after the triggering event
  (new post / new reaction) — no background job required at this scale.
- **Top Contributors** is a live query (`app/services/leaderboard.py`), not
  a stored table: `score = posts×3 + likes×1 − reports×2`. Adjust the
  weights there if the balance feels off once real usage comes in.
- **Constitution** is stored in the DB (`site_constitution` table, versioned)
  and rendered from Markdown, so you can update it later without a
  redeploy — see the "Editing the constitution" section below.

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
flask seed --admin-email you@juw.edu.pk --admin-password "ChooseAStrongOne1"

flask run
```

Visit `http://127.0.0.1:5000`. Log in with the admin account you just seeded
to approve student registrations and moderate reports at `/admin`.

## Deploying to Render + Neon

1. **Create the Neon database** (if you haven't already) and copy its
   connection string — it looks like
   `postgresql://user:password@host/dbname?sslmode=require`.
2. **Push this repo to GitHub.**
3. **On Render**: New → Web Service → connect the repo. Render will pick up
   `render.yaml` automatically (Blueprint), or configure manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `flask db upgrade && gunicorn wsgi:app`
   - Environment variables:
     - `DATABASE_URL` → your Neon connection string
     - `SECRET_KEY` → Render can auto-generate this (already set in
       `render.yaml`)
     - `FLASK_APP` → `wsgi.py`
4. **After first deploy**, seed the starter data and your admin account by
   running (Render Shell, or a one-off job):
   ```bash
   flask seed --admin-email you@juw.edu.pk --admin-password "ChooseAStrongOne1"
   ```
   Re-running `flask seed` later is safe — it only creates what's missing
   and won't duplicate communities/categories/badges.

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

## What's intentionally out of scope for this version

- Editor rotation / student moderator roles — you assign roles manually for
  now; there's no rotation scheduler.
- Nested comment threads — comments are flat by design.
- Free-text tags — categories are a controlled list per community, editable
  by directly updating the `community_categories` table (or ask for a small
  admin UI for this once you know which tags communities actually want).

## Project layout

```
app/
  blueprints/       # auth, communities, posts, admin, main
  services/         # badges.py, leaderboard.py, seed.py
  templates/
  static/css/
  models.py
  extensions.py
config.py            # POST_MAX_CHARS, BADGE_RULES live here
wsgi.py               # gunicorn entry point
render.yaml
```
