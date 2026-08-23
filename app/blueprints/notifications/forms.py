from flask_wtf import FlaskForm
from wtforms import BooleanField, SubmitField


class NotificationPreferencesForm(FlaskForm):
    events_new = BooleanField("New Events")
    events_reminders = BooleanField("Event Reminders")

    bethak_opens = BooleanField("Bethak Opens")

    literary_new_publications = BooleanField("New Publications")
    literary_editors_picks = BooleanField("Editor's Picks")

    activity_submission_approved = BooleanField("Submission Approved")
    activity_submission_rejected = BooleanField("Submission Rejected")
    activity_changes_requested = BooleanField("Changes Requested")

    community_comments = BooleanField("Comments & Replies")

    system_announcements = BooleanField("Important Announcements")

    submit = SubmitField("Save Preferences")
