from mongoengine import Document, StringField, URLField, ListField, ReferenceField, DateTimeField, BooleanField, IntField, EmbeddedDocument, EmbeddedDocumentField
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin


class User(UserMixin, Document):
    email = StringField(required=True, unique=True)
    password_hash = StringField()
    first_name = StringField()
    last_name = StringField()
    is_active = BooleanField(default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    facebook_token = StringField(max_length=200)


class Video(Document):
    video_id = StringField(required=True)
    title = StringField(required=True)
    channel_title = StringField()
    channel_icon_url = StringField()
    transcription = StringField()
    link = URLField()
    tags = ListField(StringField())
    thumbnail = StringField()
    duration = IntField()  # potresti voler salvare la durata in secondi, ad esempio
    is_article_created = BooleanField(default=False)


class Outline(EmbeddedDocument):
    title = StringField(required=True)
    description = StringField(required=True)
    content = StringField(required=True)
    photo = StringField()


class Category(Document):
    # Il nome della categoria, ad es. "Investimenti"
    name = StringField(required=True, unique=True)
    slug = StringField(required=True, unique=True)
    color = StringField(required=True, unique=True)
    description = StringField()  # Una breve descrizione della categoria (opzionale)


class Article(Document):
    # Supponendo che tu abbia una classe User come modello di riferimento
    author = ReferenceField('User')
    # Supponendo che tu abbia una classe Video come modello di riferimento
    video = ReferenceField('Video')
    main_photo = StringField()
    category = ReferenceField('Category', required=True)
    title = StringField(required=True)
    slug = StringField(required=True, unique=True)
    keyword = StringField(required=True)
    meta_description = StringField(required=True)
    h1 = StringField(required=True)
    article_intro = StringField(required=True)
    outlines = ListField(EmbeddedDocumentField(Outline))
    created_at = DateTimeField(default=datetime.utcnow)
    published = BooleanField(default=False)
    published_at = DateTimeField()
    views = IntField(default=0)
    link_article = StringField()


class Website(Document):
    site_name = StringField(required=True, unique=True)
    database_name = StringField(required=True)

    def __str__(self):
        return f"Website: {self.site_name}, Database: {self.database_name}"
