from flask import current_app
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Length
from wtforms.widgets import ListWidget, CheckboxInput


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Your piece", validators=[DataRequired()])
    categories = MultiCheckboxField("Tags", coerce=int)
    submit = SubmitField("Publish")

    def validate_body(self, field):
        max_chars = current_app.config["POST_MAX_CHARS"]
        if field.data and len(field.data) > max_chars:
            from wtforms.validators import ValidationError
            raise ValidationError(f"Posts are limited to {max_chars} characters (yours is {len(field.data)}).")


class CommentForm(FlaskForm):
    body = StringField("Add a comment", validators=[DataRequired(), Length(max=500)])
    submit = SubmitField("Comment")
