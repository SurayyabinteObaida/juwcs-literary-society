from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def approved_required(view_func):
    """Blocks pending/rejected users from member-only actions (posting, commenting, reacting)."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_approved:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped
