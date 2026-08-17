# Firebase Cloud Messaging — JUWCS Literary Society

This document explains how push notifications are wired into the existing
Flask app, how to configure Firebase, and how to test each notification
type end-to-end.

Nothing here is a separate app — it's integrated directly into the existing
Flask/Jinja2/SQLAlchemy project: same blueprints pattern, same
Flask-Migrate history, same theme system, same navbar.

---

## 1. How it fits together

```
Firebase Web SDK (browser, modular v9+)
    -> firebase-messaging-sw.js (service worker, served at /)
    -> Notification permission + FCM token
    -> POST /notifications/register  (Flask)
    -> PushSubscription row (tied to the logged-in user)

Editor/Admin action commits to the DB
    -> app/services/notification_service.py (notify_*)
    -> Notification row (in-app center)
    -> app/services/firebase_service.py (Firebase Admin SDK, Python)
    -> FCM -> browser push
```

Key files:

| Purpose | Path |
|---|---|
| Push/notification/preference models | `app/models.py` (bottom section) |
| Firebase Admin (server-side send) | `app/services/firebase_service.py` |
| Central notification logic | `app/services/notification_service.py` |
| Routes: register/unregister/list/preferences/test | `app/blueprints/notifications/` |
| Frontend Firebase init (modular SDK, ESM) | `app/static/js/firebase-init.js` |
| Opt-in prompt, bell, toasts, token lifecycle | `app/static/js/notifications.js` |
| Background push handling | `app/static/firebase-messaging-sw.js` (served at `/firebase-messaging-sw.js`) |
| Reminder cron entrypoint | `flask notify-event-reminders` (in `app/__init__.py`) |

---

## 2. Local setup

```bash
pip install -r requirements.txt
flask db upgrade
flask run
```

Without Firebase server credentials configured, the site runs completely
normally — in-app notifications (the bell) still work, and push sends are
skipped with a log line, never an error shown to users.

---

## 3. Firebase setup

The project already points at the `juw-literary-society` Firebase project
(client-side config is baked into `config.py` / the service worker — it's
not a secret). You only need to add **server** credentials:

1. Firebase Console -> Project Settings -> **Service accounts**.
2. Click **Generate new private key** -> downloads a JSON file.
3. From that JSON, copy `project_id`, `client_email`, and `private_key`
   into the three env vars below. **Do not commit the JSON file.**
4. Firebase Console -> Project Settings -> **Cloud Messaging** -> Web
   configuration -> Web Push certificates. The VAPID key is already set as
   the default for `FIREBASE_VAPID_PUBLIC_KEY` in `config.py`; only
   override it if you rotate the key.

---

## 4. Environment variables

See `.env.example` for the full list. The three that matter:

```
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CLIENT_EMAIL=firebase-adminsdk-xxxx@your-project-id.iam.gserviceaccount.com
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

- Never put real values in `.env.example`, in git, in frontend JS, or in
  templates.
- `FIREBASE_PRIVATE_KEY` works whether your platform stores real newlines
  or literal `\n` — `firebase_service.py` normalizes both.
- Add `.env` and any downloaded service-account JSON to `.gitignore`
  (already done).

---

## 5. Browser setup (what the end user does)

```
Log in
  -> "Stay Connected with JUWCS" prompt appears
  -> Click "Enable Notifications"
  -> Browser's native permission dialog appears
  -> Allow
  -> "✓ Notifications Enabled"
```

No token copy/paste, no Firebase Console visit. Behind the scenes:
`notifications.js` requests permission, registers
`/firebase-messaging-sw.js` at root scope, obtains an FCM token via the
modular SDK's `getToken()`, and POSTs it to `/notifications/register`,
which upserts a `PushSubscription` row tied to `current_user`.

On every later page load, if permission is already `granted`, the same
flow re-runs silently to keep the registration fresh (Firebase can rotate
tokens).

**Account switching on a shared browser:** logging out fires a best-effort
`/notifications/unregister` call (disabling that browser's subscription)
before navigating away, and `/notifications/register` always reassigns a
token to whichever user is currently logged in — so a second user on the
same machine can never receive the first user's private notifications.

---

## 6. Notification categories & preferences

Members can turn categories on/off at **Profile -> Settings ->
Notifications** (`/notifications/preferences`). Everything defaults to on.
Categories map to `NotificationPreference` columns; see
`NOTIFICATION_PREFERENCE_MAP` in `app/models.py`.

---

## 7. Testing each trigger

### Test notification (fastest way to confirm Firebase works)
Admin Dashboard -> **Notification Testing** -> Send Test Notification.
Sends only to the admin's own registered devices.

### Digital Bethak
Admin opens (or reopens after it was closed) a Bethak session
(`/bethak/create` or the Reopen button). Notified: all approved members
who haven't opted out. Re-saving an already-open session sends nothing
(only a `CLOSED -> OPEN` transition fires).

### Event created
Editor/Admin creates an event and publishes it (or edits a draft into
`published`). Notified: all approved members.

### Event registration
A member registers for a published event. Notified: that member only,
immediately.

### Event reminders (24h / 1h)
Not fired synchronously — run periodically:

```bash
flask notify-event-reminders
```

Idempotent via `NotificationDedupe`, so it's safe to run on a schedule
(Render Cron Job, `*/15 * * * *` is configured in `render.yaml`) without
ever double-sending, even if two ticks overlap or the DB has multiple
Gunicorn workers behind the web service.

### Post approved / rejected / changes requested
Editor Desk -> review a pending submission -> Approve, Reject (with
feedback), or Request Changes. Notified: the post's author only.

### Editor's Pick / new publication
Editor Desk -> Highlights -> publish a highlight. Notified: all approved
members who haven't opted out of "Editor's Picks".

---

## 8. Failure handling

- A Firebase/FCM failure never rolls back or blocks the underlying action
  (Bethak still opens, event still gets created, etc.) — the DB commit
  always happens first; notification sending happens after and is wrapped
  so it can't raise into the request.
- Invalid/unregistered FCM tokens are automatically disabled on the
  `PushSubscription` row so they stop being retried.
- Failures are logged server-side (`logger.warning` / `logger.exception`)
  — never surfaced to the user, and Firebase credentials/errors are never
  included in any user-facing response.

---

## 9. Render deployment

`render.yaml` defines:

- **`literary-society`** (web) — add `FIREBASE_PROJECT_ID`,
  `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY` as secret env vars in the
  Render dashboard (marked `sync: false`, so Render will prompt you for
  values instead of committing them).
- **`literary-society-event-reminders`** (cron, `*/15 * * * *`) — runs
  `flask notify-event-reminders` as an independent scheduled job, not
  inside the web service's Gunicorn workers, so reminders fire exactly
  once per tick regardless of how many web instances/workers are running.
  Needs the same three Firebase env vars plus `DATABASE_URL`.

---

## 10. Security notes

- `FIREBASE_PRIVATE_KEY` and friends are read from environment variables
  only — never hardcoded, never logged, never sent to the frontend.
- The VAPID key is public by design (it identifies the sender to the
  browser's push service) and is safe to ship in client JS.
- `/notifications/register`, `/unregister`, `/list`, `/<id>/read`,
  `/read-all`, `/preferences`, and `/test` all require login
  (`@login_required`); `/test` additionally requires admin
  (`@admin_required`) and only ever targets the caller's own devices.
- The JSON API routes under `/notifications/` validate a CSRF token
  (read from the page's `<meta name="csrf-token">` tag) on every
  state-changing request, the same `SECRET_KEY`-backed token Flask-WTF
  already issues elsewhere in the app.
