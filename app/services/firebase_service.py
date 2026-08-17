"""
Firebase Admin SDK integration (Python).

Reusable, lazily-initialized service for sending FCM push notifications from
the backend. Credentials come from environment variables only — never from a
committed service-account JSON file (see docs/FCM_NOTIFICATIONS.md).

This module is intentionally defensive: if Firebase isn't configured, or a
send fails, callers get back a result object instead of an exception. Push
delivery must never be allowed to break the website action that triggered it
(see requirement: "Database action succeeds, Firebase fails, website action
remains successful").
"""
import logging

from flask import current_app

logger = logging.getLogger("juwcs.firebase")

_firebase_app = None
_init_attempted = False


def _get_credential_dict():
    project_id = current_app.config.get("FIREBASE_PROJECT_ID")
    client_email = current_app.config.get("FIREBASE_CLIENT_EMAIL")
    private_key = current_app.config.get("FIREBASE_PRIVATE_KEY")

    if not (project_id and client_email and private_key):
        return None

    # Render/Heroku-style env vars store the key with literal "\n" sequences
    # instead of real newlines — normalize either form.
    private_key = private_key.replace("\\n", "\n")

    return {
        "type": "service_account",
        "project_id": project_id,
        "private_key": private_key,
        "client_email": client_email,
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def is_configured():
    return _get_credential_dict() is not None


def _get_app():
    """Initialize (once) and return the Firebase Admin App, or None if the
    server credentials aren't configured in this environment."""
    global _firebase_app, _init_attempted

    if _firebase_app is not None:
        return _firebase_app
    if _init_attempted:
        return None

    _init_attempted = True

    cred_dict = _get_credential_dict()
    if cred_dict is None:
        logger.warning(
            "Firebase Admin not configured — FIREBASE_PROJECT_ID / "
            "FIREBASE_CLIENT_EMAIL / FIREBASE_PRIVATE_KEY are missing. "
            "Push notifications will be skipped; in-app notifications still work."
        )
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred, name="juwcs")
        return _firebase_app
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")
        _firebase_app = None
        return None


class PushSendResult:
    def __init__(self):
        self.success_tokens = []
        self.invalid_tokens = []   # tokens Firebase says are no longer valid — caller should disable them
        self.failed_tokens = []    # tokens that failed for another (possibly transient) reason
        self.attempted = False
        self.error = None


def send_push_to_tokens(tokens, title, body, link=None, data=None, icon=None):
    """Send one push notification to a list of FCM registration tokens.

    Never raises — failures are captured on the returned PushSendResult so
    callers can log them and keep the triggering website action successful.
    """
    result = PushSendResult()
    tokens = [t for t in (tokens or []) if t]
    if not tokens:
        return result

    app = _get_app()
    if app is None:
        return result  # not configured — silently skip, in-app notification already saved

    result.attempted = True

    try:
        from firebase_admin import messaging

        payload_data = {str(k): str(v) for k, v in (data or {}).items()}
        if link:
            payload_data["link"] = link
        if icon:
            payload_data["icon"] = icon
        payload_data["title"] = title
        payload_data["body"] = body

        for token in tokens:
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                webpush=messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(link=link) if link else None,
                    notification=messaging.WebpushNotification(
                        icon=icon or "/static/img/favicon.svg",
                    ),
                ),
            )
            try:
                messaging.send(message, app=app)
                result.success_tokens.append(token)
            except messaging.UnregisteredError:
                result.invalid_tokens.append(token)
            except Exception as exc:  # noqa: BLE001 - one bad token must not stop the batch
                # firebase_admin raises typed exceptions with `.code`; treat
                # registration-shaped errors as invalid, everything else as a
                # (loggable, possibly transient) failure.
                code = getattr(exc, "code", "") or ""
                if code in ("NOT_FOUND", "UNREGISTERED", "INVALID_ARGUMENT"):
                    result.invalid_tokens.append(token)
                else:
                    result.failed_tokens.append(token)
                    logger.warning("FCM send failed for a token: %s", exc)
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
        logger.exception("Unexpected error sending FCM push")

    return result
