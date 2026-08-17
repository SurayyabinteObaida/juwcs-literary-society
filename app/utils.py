import os
from functools import wraps

from flask import abort, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename


def admin_required(view_func):
    """Admin-only. Highest authority — system control, editor management."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def editor_required(view_func):
    """Editor or Admin. Content moderation / editorial review routes."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_editor_or_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Generic guard: allow only the given role value(s), e.g. roles_required('admin')."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def approved_required(view_func):
    """Blocks unapproved/disabled users from member-only actions (posting, commenting, reacting)."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_approved:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


class UploadError(ValueError):
    """Raised when an uploaded image fails validation."""


_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _validate_uploaded_image(file_storage):
    """Run all validation checks on an uploaded image and return its raw
    bytes, safe filename, and MIME type. Raises UploadError on any failure.

    - Checks file extension AND browser-reported MIME type against an allowlist.
    - Re-checks the real file size after reading (never trusts Content-Length alone).
    - Sniffs the actual file bytes so a renamed .exe can't sneak through as .png.
    - Never trusts the original filename for anything but the extension.
    """
    if file_storage is None or not file_storage.filename:
        raise UploadError("Please choose an image to upload.")

    original_name = secure_filename(file_storage.filename)
    if "." not in original_name:
        raise UploadError("That file doesn't look like a valid image.")

    ext = original_name.rsplit(".", 1)[1].lower()
    allowed_ext = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    if ext not in allowed_ext:
        raise UploadError(f"Unsupported file type. Allowed: {', '.join(sorted(allowed_ext)).upper()}.")

    allowed_mime = current_app.config["ALLOWED_IMAGE_MIMETYPES"]
    if file_storage.mimetype not in allowed_mime:
        raise UploadError("That file doesn't look like a valid image.")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    max_size = current_app.config["MAX_IMAGE_SIZE_BYTES"]
    if size <= 0:
        raise UploadError("That file appears to be empty.")
    if size > max_size:
        raise UploadError(f"Image is too large. Maximum size is {max_size // (1024 * 1024)}MB.")

    # Sniff the actual bytes so a renamed .exe can't sneak through as .png
    header = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    is_valid_image = (
        header.startswith(b"\xff\xd8\xff")  # jpg
        or header.startswith(b"\x89PNG\r\n\x1a\n")  # png
        or (header[0:4] == b"RIFF" and header[8:12] == b"WEBP")  # webp
    )
    if not is_valid_image:
        raise UploadError("That file's contents don't match a supported image format.")

    data = file_storage.stream.read()
    file_storage.stream.seek(0)
    if not data:
        raise UploadError("That file appears to be empty.")

    mimetype = _MIME_BY_EXT.get(ext, file_storage.mimetype)
    return data, original_name, mimetype, len(data)


def create_stored_image(file_storage, uploaded_by_id=None):
    """Validate an uploaded image and return a new, unsaved `StoredImage`.

    The image is stored as bytes directly in the database (PostgreSQL
    BYTEA / SQLite BLOB via SQLAlchemy's LargeBinary) instead of being
    written to the filesystem, so it survives redeploys on hosts with an
    ephemeral filesystem (e.g. Render's free tier).

    The caller is responsible for `db.session.add()`-ing (and, if replacing
    an existing image, deleting the old `StoredImage` row) as part of its
    own transaction, then committing.

    Raises UploadError with a user-facing message on any validation failure.
    """
    from app.models import StoredImage  # local import avoids a circular import

    data, filename, mimetype, size = _validate_uploaded_image(file_storage)
    return StoredImage(
        filename=filename,
        mimetype=mimetype,
        data=data,
        size_bytes=size,
        uploaded_by_id=uploaded_by_id,
    )
