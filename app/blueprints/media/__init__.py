from io import BytesIO

from flask import Blueprint, abort, send_file

from app.models import StoredImage

bp = Blueprint("media", __name__)


@bp.route("/media/image/<int:image_id>")
def image(image_id):
    """Stream a stored image's bytes straight out of the database.

    Only the requested row's binary column is ever loaded into memory —
    listing/query code elsewhere should reference `image_id` and never
    touch `.data` unless it's actually rendering this route, so pages that
    just list events/highlights don't pull image bytes along for the ride.
    """
    stored = StoredImage.query.get_or_404(image_id)
    response = send_file(
        BytesIO(stored.data),
        mimetype=stored.mimetype,
        download_name=stored.filename,
        max_age=60 * 60 * 24 * 7,  # 7 days — images are replaced (new id), never mutated in place
    )
    # Images are publicly viewable content (event covers / highlight art),
    # same as if they were static files — no auth needed to view them, only
    # to upload/replace/delete them (enforced in the editor blueprint).
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response
