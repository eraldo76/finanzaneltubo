from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, validators


class VideoForm(FlaskForm):
    video_id = StringField('Enter the video URL', [
                           validators.DataRequired(), validators.URL()])
    submit = SubmitField('Submit')


class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[
                        validators.DataRequired(), validators.Email()])
    password_hash = PasswordField('Password', validators=[
                                  validators.DataRequired()])  # Campo Password
    first_name = StringField('First Name', validators=[
                             validators.DataRequired()])
    last_name = StringField('Last Name', validators=[
                            validators.DataRequired()])
    submit = SubmitField('Register')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[
                        validators.DataRequired(), validators.Email()])
    password = PasswordField('Password', validators=[
                             validators.DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')
