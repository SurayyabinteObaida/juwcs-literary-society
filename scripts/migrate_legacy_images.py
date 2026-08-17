"""
One-time import utility: reads any images still sitting in the old
app/static/uploads/ filesystem folder and copies their bytes into the new
`stored_images` Postgres table, then points the owning Event / WeeklyHighlight
row at the new row.

This does NOT touch or delete the original files on disk — it's safe to run
more than once (already-migrated rows are skipped) and safe to run against a
database that has no legacy files at all (it'll just report 0 found).

USAGE
-----
Run this AFTER `flask db upgrade` has created the stored_images table and the
new cover_image_id / image_id columns.

    # Local (SQLite), from the project root, with your venv active:
    python scripts/migrate_legacy_images.py

    # Against Render's Postgres, from your machine (or a Render Shell):
    DATABASE_URL="postgresql://..." python scripts/migrate_legacy_images.py

Notes:
  - "DATABASE_URL" must point at the SAME database flask db upgrade ran
    against — config.py already reads this env var, so you don't need to
    change anything else.
  - If Render's filesystem was already wiped by the time you read this
    (a redeploy since the images were uploaded), the legacy files are gone
    and there is nothing to import — this script will simply report 0 found.
    That's exactly the ephemeral-filesystem problem this whole migration
    fixes going forward.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import Event, WeeklyHighlight, StoredImage


def _sniff_mimetype(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _import_one(app, legacy_relative_path, label):
    """legacy_relative_path looks like 'uploads/events/<name>.jpg' (relative
    to app/static/). Returns a StoredImage (not yet committed) or None."""
    if not legacy_relative_path:
        return None, "no legacy path on record"

    full_path = os.path.join(app.static_folder, legacy_relative_path)
    if not os.path.isfile(full_path):
        return None, f"file not found on disk: {full_path}"

    with open(full_path, "rb") as f:
        data = f.read()

    if not data:
        return None, "file is empty"

    mimetype = _sniff_mimetype(data)
    if mimetype is None:
        return None, "file contents don't match a supported image format (skipped)"

    stored = StoredImage(
        filename=os.path.basename(legacy_relative_path),
        mimetype=mimetype,
        data=data,
        size_bytes=len(data),
        uploaded_by_id=None,
    )
    return stored, None


def run():
    app = create_app()
    imported = 0
    skipped_already_migrated = 0
    failed = []

    with app.app_context():
        events = Event.query.filter(Event.cover_image_id.is_(None)).all()
        for event in events:
            if not event.legacy_cover_image_path:
                continue
            stored, error = _import_one(app, event.legacy_cover_image_path, f"Event #{event.id}")
            if error:
                failed.append((f"Event #{event.id} ({event.title!r})", error))
                continue
            db.session.add(stored)
            db.session.flush()
            event.cover_image_id = stored.id
            imported += 1
            print(f"[ok] Event #{event.id} {event.title!r} -> stored_images.id={stored.id}")

        highlights = WeeklyHighlight.query.filter(WeeklyHighlight.image_id.is_(None)).all()
        for highlight in highlights:
            if not highlight.legacy_image_path:
                continue
            stored, error = _import_one(app, highlight.legacy_image_path, f"Highlight #{highlight.id}")
            if error:
                failed.append((f"Highlight #{highlight.id} ({highlight.title!r})", error))
                continue
            db.session.add(stored)
            db.session.flush()
            highlight.image_id = stored.id
            imported += 1
            print(f"[ok] Highlight #{highlight.id} {highlight.title!r} -> stored_images.id={stored.id}")

        already_migrated_events = Event.query.filter(Event.cover_image_id.isnot(None)).count()
        already_migrated_highlights = WeeklyHighlight.query.filter(WeeklyHighlight.image_id.isnot(None)).count()
        skipped_already_migrated = already_migrated_events + already_migrated_highlights

        db.session.commit()

    print()
    print("=" * 60)
    print(f"Imported into stored_images: {imported}")
    print(f"Already had a database image (skipped):   {skipped_already_migrated}")
    print(f"Failed / skipped with a reason:            {len(failed)}")
    for name, reason in failed:
        print(f"  - {name}: {reason}")
    print("=" * 60)
    print(
        "Original files under app/static/uploads/ were NOT deleted. "
        "Review the results above, then delete that folder yourself once "
        "you're satisfied every image made it into the database."
    )


if __name__ == "__main__":
    run()
