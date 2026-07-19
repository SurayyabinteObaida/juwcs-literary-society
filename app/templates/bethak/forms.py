from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class BethakSessionForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    topic = StringField("Topic / Mazmoon (optional)", validators=[Optional(), Length(max=160)])
    description = TextAreaField("Description (optional)", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Open Bethak")


class BethakEntryForm(FlaskForm):
    text = TextAreaField("Your sher / line", validators=[DataRequired(), Length(max=400)])
    submit = SubmitField("Post")
