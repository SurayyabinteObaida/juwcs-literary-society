from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp

from app.models import THEME_CHOICES


class ProfileForm(FlaskForm):
    name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=60),
            Regexp(r"^[a-zA-Z0-9._-]+$", message="Letters, numbers, dots, underscores, and hyphens only."),
        ],
    )
    bio = TextAreaField("Short Bio", validators=[Optional(), Length(max=500)])
    interests = StringField(
        "Literary interests / favorite genres",
        validators=[Optional(), Length(max=300)],
    )
    avatar_url = StringField("Avatar image URL (optional)", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save Profile")


class ThemeForm(FlaskForm):
    theme = SelectField("Theme", choices=THEME_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Apply Theme")
