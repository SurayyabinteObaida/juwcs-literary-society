from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, IntegerField,
    DateTimeField, SubmitField, BooleanField,
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange

from app.models import EventCategory, EVENT_CATEGORY_LABELS, HighlightCategory, HIGHLIGHT_CATEGORY_LABELS


class EventForm(FlaskForm):
    title = StringField("Event title", validators=[DataRequired(), Length(max=200)])
    category = SelectField(
        "Category",
        choices=[(c.value, EVENT_CATEGORY_LABELS[c.value]) for c in EventCategory],
        validators=[DataRequired()],
    )
    description = TextAreaField("Description", validators=[DataRequired()])
    cover_image = FileField(
        "Cover image",
        validators=[FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only (JPG, PNG, WEBP).")],
    )
    venue = StringField("Venue", validators=[DataRequired(), Length(max=200)])
    organizer = StringField("Organizer", validators=[Optional(), Length(max=160)])
    start_at = DateTimeField("Starts at", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    end_at = DateTimeField("Ends at", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    registration_deadline = DateTimeField(
        "Registration deadline", format="%Y-%m-%dT%H:%M", validators=[Optional()],
    )
    capacity = IntegerField("Capacity (leave blank for unlimited)", validators=[Optional(), NumberRange(min=1)])
    publish = BooleanField("Publish immediately (uncheck to save as draft)", default=True)
    submit = SubmitField("Save event")


class HighlightForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    category = SelectField(
        "Category",
        choices=[(c.value, HIGHLIGHT_CATEGORY_LABELS[c.value]) for c in HighlightCategory],
        validators=[DataRequired()],
    )
    description = TextAreaField("Short editorial description", validators=[DataRequired(), Length(max=600)])
    editorial_note = TextAreaField("Editor's note (optional)", validators=[Optional(), Length(max=600)])
    contributor_name = StringField("Contributor name", validators=[Optional(), Length(max=160)])
    image = FileField(
        "Image",
        validators=[FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only (JPG, PNG, WEBP).")],
    )
    publish = BooleanField("Publish immediately (uncheck to save as draft)", default=True)
    submit = SubmitField("Save highlight")
