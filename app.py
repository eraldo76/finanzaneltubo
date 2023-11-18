# Assumendo che tu stia usando la libreria "python-slugify"
from slugify import slugify
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash, get_flashed_messages, abort, g
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email
from flask_dance.contrib.facebook import make_facebook_blueprint
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from flask_dance.consumer import OAuth2ConsumerBlueprint
from flask_dance.consumer.storage import MemoryStorage
from flask_pymongo import pymongo
from models import User, Video, Article, Outline, Category
from mongoengine import connect
from forms import VideoForm, RegistrationForm, LoginForm
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from settings import YOUTUBE_API_KEY, SECRET_KEY, PEXELS_API_KEY, PEXELS_BASE_URL, MONGODB_USERNAME, MONGODB_PASSWORD
import requests
import json
import logging
import logging.handlers
from urllib.parse import urlparse, parse_qs
import isodate
import youtube_dl
from slugify import slugify
from datetime import datetime
from article_generation import step2, step3, step4, summarize_transcription
app = Flask(__name__)

# Configura la chiave segreta
app.config['SECRET_KEY'] = SECRET_KEY
app.secret_key = SECRET_KEY
# Configurazione del logging
log_formatter = logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
log_file = 'application.log'  # Definisci il nome del file di log

file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=100000, backupCount=10)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# Nome del database
db_user = MONGODB_USERNAME
db_password = MONGODB_PASSWORD
db_name = 'ServerlessInstance0'
mongo_uri = "mongodb+srv://Eraldo:gileja23!@serverlessinstance0.2edd7v9.mongodb.net/"

# Stabilisci la connessione con MongoDB locale
connect(db=db_name, host=mongo_uri, alias='default')


login_manager = LoginManager(app)
# Redirect to register view if user is not logged in
login_manager.login_view = "login"


# Crea l'oggetto blueprint per l'autenticazione Facebook
facebook_bp = OAuth2ConsumerBlueprint(
    "facebook", __name__,
    client_id='your-client-id',
    client_secret='your-client-secret',
    scope=["email", "public_profile"],
    base_url="https://graph.facebook.com/",
    authorization_url="https://www.facebook.com/dialog/oauth",
    token_url="/oauth/access_token",
    redirect_url="/",
    storage=MemoryStorage(),
)

app.register_blueprint(facebook_bp, url_prefix="/login")


@app.context_processor
def inject_categories():
    g.categories = Category.objects.all()
    return dict(categories=g.categories)


@app.route('/')
def home():
    # Recupera gli ultimi 10 articoli pubblicati dal database
    articles = Article.objects(published=True).order_by(
        '-published_at').limit(10)

    # Prepara i dati degli articoli per categoria
    per_page = 10  # numero di articoli per pagina
    categories = Category.objects.all()
    data = []

    for category in categories:
        category_articles = Article.objects(
            category=category, published=True).order_by('-published_at').limit(per_page)
        data.append({
            'category_name': category.name,
            'category_slug': category.slug,  # Aggiungi lo slug della categoria qui
            'articles': [
                {
                    'title': a.title,
                    'intro': a.article_intro,
                    'slug': a.slug,
                    'main_photo': a.main_photo,
                    'published_at': a.published_at,
                    'video': {
                        'channel_icon_url': a.video.channel_icon_url if a.video else None,
                        'channel_title': a.video.channel_title if a.video else None
                    }
                }
                for a in category_articles]})

    return render_template('frontend/home.html', articles=articles, data=data)


@app.route('/<category_name>/<article_slug>')
def post(category_name, article_slug):
    # Trova l'articolo corrispondente al nome della categoria e allo slug
    category = Category.objects(slug=category_name).first()
    if not category:
        abort(404)  # Se la categoria non esiste, restituisci un errore 404

    article = Article.objects(
        category=category, slug=article_slug, published=True).first()
    if not article:
        # Se l'articolo non esiste o non è pubblicato, restituisci un errore 404
        abort(404)

    # Recupera altri video/articoli dalla stessa categoria, escludendo l'articolo corrente
    related_videos = Article.objects(category=category, published=True, __raw__={
                                     '_id': {'$ne': article.id}}).order_by('-published_at').limit(10)

    # Formatta la durata dei video in minuti e secondi
    for related_article in related_videos:
        if related_article.video and related_article.video.duration:
            duration_seconds = related_article.video.duration
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            related_article.video.formatted_duration = f"{minutes}:{seconds:02d}"

    article.views += 1
    article.save()

    return render_template('frontend/post.html', article=article, related_videos=related_videos)


@login_manager.user_loader
def load_user(user_id):
    return User.objects(pk=user_id).first()


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data
        )
        # imposta l'hash della password
        user.set_password(form.password_hash.data)
        user.save()
        # Log in the user
        login_user(user)
        # reindirizza all'utente alla dashboard
        return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.objects(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('login.html', form=form)


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/video', methods=['GET', 'POST'])
@login_required
def video():
    form = VideoForm()
    video_info = {}  # Initialize the variable video_info as an empty dictionary

    if form.validate_on_submit():
        video_url = form.video_id.data
        payload = {'video_id': video_url}
        headers = {'Content-Type': 'application/json'}
        base_url = request.url_root  # Get the current base URL
        response = requests.post(
            f"{base_url}get_video_info", data=json.dumps(payload), headers=headers)

        # Verifica la risposta prima di decodificarla come JSON
        if response.status_code == 200:
            video_info = response.json()
        else:
            app.logger.error(
                f"Errore nella richiesta: {response.status_code} - {response.text}")

    # Inserisci la riga di logging qui
    app.logger.info(f"video_info: {video_info}")

    return render_template('video.html', form=form, video_info=video_info)


@app.route('/get_video_info', methods=['POST'])
def fetch_video_info():
    video_id_or_url = request.json.get('video_id')
    original_url = video_id_or_url
    video_id = None
    app.logger.debug(f"Fetching video info for ID or URL: {video_id_or_url}")

    if video_id_or_url is not None:
        if 'http' in video_id_or_url:
            video_id = get_youtube_video_id(video_id_or_url)
        else:
            video_id = video_id_or_url

    app.logger.debug(f"Video ID: {video_id}")

    session['video_id'] = video_id

    if video_id is None:
        return jsonify({'error': 'URL del video non valido'})

    # Get video transcript
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=['it', 'en', 'es', 'de'])
        transcript = " ".join([x['text'] for x in transcript_list])
    except Exception as e:
        transcript = str(e)
        app.logger.error(f"Error getting transcript: {str(e)}")

    api_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id={video_id}&key={YOUTUBE_API_KEY}"
    response = requests.get(api_url)

    if response.status_code != 200:
        app.logger.error(
            f"Response status code: {response.status_code}, text: {response.text}")
        return jsonify({'error': 'Errore nel recupero delle informazioni dal server YouTube'})

    if not response.content:
        app.logger.error("Risposta vuota ricevuta.")
        return jsonify({'error': 'Risposta vuota ricevuta dal server YouTube'})

    try:
        data = response.json()
    except json.JSONDecodeError:
        app.logger.error(
            f"Error decoding JSON. Response text: {response.text}")
        return jsonify({'error': 'Errore durante la decodifica della risposta JSON'})

    if 'items' not in data or not data['items']:
        app.logger.error(f"No 'items' key in data or it's empty. Data: {data}")
        return jsonify({'error': 'No video information returned from YouTube API'})

    channel_id = data['items'][0]['snippet']['channelId']
    channel_api_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={channel_id}&key={YOUTUBE_API_KEY}"
    channel_response = requests.get(channel_api_url)

    if channel_response.status_code != 200:
        app.logger.error(
            f"Channel response status code: {channel_response.status_code}, text: {channel_response.text}")
        return jsonify({'error': 'Errore nel recupero delle informazioni sul canale da YouTube'})

    channel_data = channel_response.json()
    channel_icon_url = channel_data['items'][0]['snippet']['thumbnails']['default']['url']

    title = data['items'][0]['snippet']['title']
    thumbnail_url = data['items'][0]['snippet']['thumbnails']['medium']['url']
    channel_title = data['items'][0]['snippet']['channelTitle']
    duration = data['items'][0]['contentDetails']['duration']
    duration_timedelta = isodate.parse_duration(duration)
    duration_seconds = duration_timedelta.total_seconds()

    try:
        tags = data['items'][0]['snippet']['tags']
    except KeyError:
        tags = []

    ydl_opts = {
        'ignoreerrors': True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(video_id, download=False)
    if info_dict is not None:
        formats = info_dict.get('formats', [])
        format_info = [
            {
                'format_id': format["format_id"],
                'format_note': format["format_note"],
                'ext': format["ext"],
                'url': format['url']
            }
            for format in formats if format["acodec"] != "none"
        ]
    else:
        format_info = []  # Set format_info as an empty list if info_dict is None

    video_info = {
        'video_id': video_id,
        'link': original_url,
        'transcript': transcript,
        'tags': tags,
        'title': title,
        'channel_title': channel_title,
        'channel_icon_url': channel_icon_url,  # Added this
        'thumbnail': thumbnail_url,
        'duration': int(duration_seconds),
        'formats': format_info,
    }

    return jsonify(video_info) if video_info else jsonify({'error': 'Impossibile ottenere le informazioni del video'})


def get_youtube_video_id(url):
    app.logger.debug(f"get_youtube_video_id called with url: {url}")
    query = urlparse(url)
    video_id = None

    app.logger.debug(f"query.hostname: {query.hostname}")
    app.logger.debug(f"query.path: {query.path}")

    if query.hostname == 'youtu.be':
        video_id = query.path[1:]
    elif query.hostname in {'www.youtube.com', 'youtube.com', 'music.youtube.com'}:
        if query.path == '/watch':
            video_id = parse_qs(query.query)['v'][0]
        elif query.path[:3] == '/v/':
            video_id = query.path.split('/')[2]
        elif query.path[:7] == '/embed/':
            video_id = query.path.split('/')[2]
        elif query.path[:7] == '/shorts/':  # Add this condition
            # Add this line to remove "?feature=share"
            video_id = query.path.split('/')[2].split('?')[0]

    if video_id:
        app.logger.debug(f"Video ID: {video_id}")
    else:
        app.logger.debug("No video ID extracted")

    return video_id

# salviamo il video nel db di mongo


def save_video_info_to_db(video_info):
    print(video_info)
    # Controlla se il video esiste già usando l'ID del video
    existing_video = Video.objects(video_id=video_info['video_id']).first()

    if existing_video:
        # Notifica all'utente
        flash('Il video esiste già. Vuoi aggiornarlo?', 'warning')
        return None

    # Se il video non esiste, crea una nuova istanza di Video
    video = Video(
        title=video_info['title'],
        video_id=video_info['video_id'],
        channel_title=video_info['channel_title'],
        # Usa .get per prevenire l'errore KeyError
        channel_icon_url=video_info.get('channel_icon_url', ''),
        link=video_info['link'],
        transcription=video_info.get('transcript', ''),
        tags=video_info.get('tags', []),
        thumbnail=video_info.get('thumbnail', ''),
        duration=video_info.get('duration', ''),
        is_article_created=False
    )
    video.save()  # Salva il video nel database

    flash('Video salvato con successo!', 'success')
    return video


@app.route('/inserisci', methods=['POST'])
@login_required
def inserisci_video():
    video_info = {
        'title': request.form['title'],
        'video_id': request.form['video_id'],
        'channel_title': request.form.get('channel_title', ''),
        'channel_icon_url': request.form.get('channel_icon_url', ''),
        'transcript': request.form['transcript'],
        'link': request.form['link'],
        'tags': request.form['tags'].split(', '),
        'thumbnail': request.form['thumbnail'],
        'duration': request.form['duration']
    }

    saved_video = save_video_info_to_db(video_info)

    if saved_video:
        # Reindirizza alla pagina listavideo
        return redirect(url_for('listavideo'))
    else:
        # Gestisci l'errore
        return "Errore nel salvataggio del video", 400


@app.route('/listavideo')
@login_required
def listavideo():
    # Recupera tutti i video dal database
    videos = Video.objects()

    # Passa i video al template
    return render_template('listavideo.html', videos=videos)


@app.route('/elimina_video/<video_id>', methods=['POST'])
@login_required
def elimina_video(video_id):
    video = Video.objects(video_id=video_id).first()

    if not video:
        flash('Video non trovato.', 'danger')
        return redirect(url_for('listavideo'))

    video.delete()
    flash('Video eliminato con successo.', 'success')
    return redirect(url_for('listavideo'))


@app.route('/visualizza_video/<video_id>', methods=['GET'])
@login_required
def visualizza_video(video_id):
    # Qui puoi ottenere i dettagli del video usando video_id
    # e poi renderizzare il template appropriato.
    video = Video.objects(video_id=video_id).first()
    if not video:
        flash('Video non trovato.', 'danger')
        return redirect(url_for('lista_video'))
    return render_template('visualizza_video.html', video=video)


@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    try:
        category_name = request.form.get('newCategory')
        if category_name:
            # Genera uno slug dalla categoria usando slugify
            slug = slugify(category_name, to_lower=True)

            # Verifica se la categoria esiste già
            existing_category = Category.objects(slug=slug).first()
            if not existing_category:
                new_category = Category(name=category_name, slug=slug)
                new_category.save()
                return jsonify(success=True, slug=slug, name=category_name)
            else:
                return jsonify(success=False, error="Categoria esistente")
        return jsonify(success=False, error="Nome categoria mancante")
    except Exception as e:
        print(e)  # Stampa l'errore sulla console
        return jsonify(success=False, error=str(e))


@app.route('/create_article/<video_id>', methods=['GET', 'POST'])
@login_required
def create_article(video_id):
    video = Video.objects(video_id=video_id).first()

    if not video:
        flash('Video non trovato.', 'danger')
        return redirect(url_for('listavideo'))

    # Preleva tutte le categorie dal database
    categories = Category.objects.all()

    # Se il metodo è POST, significa che il form è stato inviato e possiamo elaborare i dati.
    if request.method == 'POST':
        return redirect(url_for('create_article_step1', video_id=video_id))

    # Se siamo qui, allora il metodo è GET e stiamo solo visualizzando la pagina.
    return render_template('create_article.html', video_id=video_id, categories=categories)

  # Assicurati di importare session


@app.route('/create_article_step1/<video_id>', methods=['POST'])
@login_required
def create_article_step1(video_id):
    keyword = request.form.get('keyword')
    category = request.form.get('category')  # Ottieni la categoria dal form
    print("Categoria ottenuta dal form:", category)
    video = Video.objects(video_id=video_id).first()

    if not video:
        flash('Video non trovato.', 'danger')
        return redirect(url_for('listavideo'))

    action = request.form.get('action')

    if action == 'Rigenera':
        summary = summarize_transcription(request.form.get('summary'), keyword)
    elif action == 'Prossimo Step':
        # qui puoi salvare il riassunto modificato o fare altre operazioni necessarie
        session[f"summary_{video_id}"] = request.form.get(
            'summary')  # saving summary to session
        session[f"keyword_{video_id}"] = keyword  # saving keyword to session
        # saving category to session
        session[f"category_{video_id}"] = category
        return redirect(url_for('create_article_step2', video_id=video_id))
    else:
        summary = summarize_transcription(video.transcription, keyword)

    return render_template('summary_view.html', summary=summary, video_id=video_id, category=category)


@app.route('/create_article_step2/<video_id>', methods=['GET', 'POST'])
@login_required
def create_article_step2(video_id):
    # Stampa la categoria dalla sessione
    print("Categoria nella sessione (Step2):",
          session.get(f"category_{video_id}"))

    summary_key = f"summary_{video_id}"
    keyword_key = f"keyword_{video_id}"

    if request.method == 'POST':

        # Se l'utente decide di procedere allo Step 3
        if request.form.get('proceed_to_step3'):
            # Salviamo le informazioni del form nella sessione
            session[f"title_{video_id}"] = request.form.get('title', "")
            session[f"meta_description_{video_id}"] = request.form.get(
                'meta_description', "")
            session[f"h1_{video_id}"] = request.form.get('h1', "")
            session[f"article_intro_{video_id}"] = request.form.get(
                'article_intro', "")

            # Stampa il contenuto della sessione per verificare se i dati sono stati salvati correttamente
            print("Contenuto della sessione dopo aver salvato i dati del form:", session)

            return redirect(url_for('create_article_step3', video_id=video_id))

        summary = request.form.get('summary')
        keyword = request.form.get('keyword')

        results = step2(summary, keyword)
        return render_template('create_article_step2.html', video_id=video_id, results=results)

    elif summary_key in session and keyword_key in session:

        results = step2(session[summary_key], session[keyword_key])
        return render_template('create_article_step2.html', video_id=video_id, results=results)

    return "Errore: Metodo GET non supportato.", 400


@app.route('/create_article_step3/<video_id>', methods=['GET', 'POST'])
@login_required
def create_article_step3(video_id):
    print("Categoria nella sessione (Step3):",
          session.get(f"category_{video_id}"))

    print(request.form)  # Stampa il contenuto del form subito
    # Utilizza la session di Flask per ottenere i dati
    summary = session.get(f"summary_{video_id}", "")
    keyword = session.get(f"keyword_{video_id}", "")
    print("Summary in Step 3:", summary)
    print("Keyword in Step 3:", keyword)
    if request.method == "POST":
        # Estrarre gli outlines selezionati dal form
        selected_outlines = request.form.getlist('outline')

        # Salva gli outlines selezionati nella sessione
        session[f"selected_outlines_{video_id}"] = selected_outlines

        # Reindirizza allo step successivo (step4)
        return redirect(url_for('create_article_step4', video_id=video_id))

    outlines = step3(summary, keyword)
    print("Generated Outlines:", outlines)
    return render_template('step3.html', outlines=outlines, video_id=video_id)


@app.route('/create_article_step4/<video_id>', methods=['GET', 'POST'])
@login_required
def create_article_step4(video_id):
    # Stampa la sessione subito
    print(session)

    # Utilizza la session di Flask per ottenere i dati
    summary = session.get(f"summary_{video_id}", "")
    keyword = session.get(f"keyword_{video_id}", "")
    category_slug = session.get(f"category_{video_id}", "")
    selected_outlines_raw = session.get(f"selected_outlines_{video_id}", [])
    video = Video.objects(video_id=video_id).first()
    transcript_video = video.transcription
    # Stampa i dati ottenuti dalla sessione

    print("Summary:", summary)
    print("Keyword:", keyword)
    print("Category Slug:", category_slug)
    print("Raw Outlines:", selected_outlines_raw)

    # Elabora gli outlines selezionati per separare il titolo dalla descrizione
    selected_outlines = []
    for item in selected_outlines_raw:
        title, description = item.split(':', 1)
        selected_outlines.append({'title': title, 'description': description})

    print("Processed Outlines:", selected_outlines)

    content = ""
    if request.method != "POST":
        content = step4(transcript_video, keyword, selected_outlines)
        print("Generated Content:", content)
    elif request.form.get('form_submitted') == "yes":
        content = request.form.get('generated_content')
        outline = Outline(title="Sommario",
                          description="descrizione", content=content)

        video_instance = Video.objects(video_id=video_id).first()
        category_instance = Category.objects(slug=category_slug).first()

        if video_instance and category_instance:
            article = Article(
                author=current_user.id,
                video=video_instance,
                category=category_instance,
                title=session.get(f"title_{video_id}", ""),
                keyword=keyword,
                meta_description=session.get(
                    f"meta_description_{video_id}", ""),
                h1=session.get(f"h1_{video_id}", ""),
                article_intro=session.get(f"article_intro_{video_id}", ""),
                outlines=[outline]  # Una sola voce nella lista
            )

            # Genera lo slug
            article_slug = slugify(article.title, to_lower=True)
            # Verifica l'unicità dello slug e, se necessario, aggiungi un suffisso
            suffix = 1
            original_slug = article_slug
            while Article.objects(slug=article_slug).first():
                article_slug = f"{original_slug}-{suffix}"
                suffix += 1
            article.slug = article_slug

            try:
                article.save()
                flash('Articolo salvato con successo nel database.', 'success')

                session_keys_to_delete = [
                    f"summary_{video_id}",
                    f"keyword_{video_id}",
                    f"category_{video_id}",
                    f"selected_outlines_{video_id}",
                    f"title_{video_id}",
                    f"meta_description_{video_id}",
                    f"h1_{video_id}",
                    f"article_intro_{video_id}"
                ]

                for key in session_keys_to_delete:
                    if key in session:
                        session.pop(key)

                return redirect(url_for('dashboard'))
            except Exception as e:
                print("Errore durante il salvataggio:", str(e))
                flash(
                    'Errore durante il salvataggio dell\'articolo nel database: ' + str(e), 'danger')
        else:
            flash('Errore durante il salvataggio dell\'articolo nel database.', 'danger')

    return render_template('create_article_step4.html', content=content, video_id=video_id)


@app.route('/articles', methods=['GET'])
@login_required
def articles():
    # Query per ottenere tutti gli articoli in ordine crescente di creazione
    all_articles = Article.objects().order_by('created_at')

    return render_template('articles.html', articles=all_articles)


@app.route('/article/<slug>')
@login_required
def view_article(slug):
    # Cerca l'articolo nel database utilizzando lo slug
    article = Article.objects(slug=slug).first()

    # Se l'articolo non esiste, restituisci una pagina di errore 404
    if not article:
        abort(404, description="Articolo non trovato")

    # Altrimenti, passa l'articolo al template e restituisci la pagina dell'articolo
    return render_template('article_view.html', article=article)


@app.route('/save_image_in_session', methods=['POST'])
def save_image_in_session():
    imageUrl = request.form.get('imageUrl')
    if not imageUrl:
        return jsonify(success=False, message="URL dell'immagine non fornito.")

    # Salva l'URL nell'elenco delle immagini in sessione
    if 'selected_images' not in session:
        session['selected_images'] = []
    session['selected_images'].append(imageUrl)
    session.modified = True

    return jsonify(success=True, message="URL dell'immagine salvato con successo.")


@app.route('/article/edit/<slug>', methods=['GET', 'POST'])
@login_required
def edit_article(slug):
    article = Article.objects(slug=slug).first()

    if not article:
        abort(404, description="Articolo non trovato")

    if request.method == "POST":
        # Aggiorna l'articolo con i nuovi dati inviati dal modulo
        article.title = request.form.get('title')
        article.keyword = request.form.get('keyword')
        article.meta_description = request.form.get('meta_description')
        article.h1 = request.form.get('h1')
        article.article_intro = request.form.get('article_intro')

        # Aggiorna la categoria dell'articolo
        category_id = request.form.get('category')
        category = Category.objects(id=category_id).first()
        if category:
            article.category = category
        else:
            flash('Categoria selezionata non valida.', 'danger')
            return render_template('edit_article.html', article=article, categories=Category.objects.all())

        # Aggiorna gli outline dell'articolo
        outlines = []
        selected_images = [request.form.get(
            f'selectedImageUrl_{i}') for i in range(1, 6)]

        for i in range(1, 6):
            outline_title = request.form.get(f'outline_{i}_title')
            outline_description = request.form.get(f'outline_{i}_description')
            outline_content = request.form.get(f'outline_{i}_content')

            if outline_title and outline_description and outline_content:
                # Crea una nuova istanza di Outline
                outline_instance = Outline(
                    title=outline_title,
                    description=outline_description,
                    content=outline_content
                )

                # Aggiungi l'URL dell'immagine all'outline, se disponibile
                outline_image = selected_images.pop(
                    0) if selected_images else None
                outline_instance.photo = outline_image

                outlines.append(outline_instance)
        article.outlines = outlines
        main_image_url = request.form.get('mainImageUrl')
        if main_image_url:
            article.main_photo = main_image_url
        # Genera un nuovo slug
        new_slug = slugify(article.title)
        if new_slug != article.slug:
            # Se il nuovo slug è diverso dallo slug corrente, aggiorna lo slug
            article.slug = new_slug

        # Salva le modifiche nel database
        try:
            article.save()
            flash('Articolo aggiornato con successo!', 'success')
            # Usa il nuovo slug per il reindirizzamento
            return redirect(url_for('view_article', slug=article.slug))
        except Exception as e:
            flash(
                f'Errore durante l\'aggiornamento dell\'articolo: {str(e)}', 'danger')

    # Passa anche le categorie al template
    return render_template('edit_article.html', article=article, categories=Category.objects.all())


@app.route('/article/publish/<slug>', methods=['POST'])
@login_required
def publish_article(slug):
    article = Article.objects(slug=slug).first()

    if not article:
        abort(404, description="Articolo non trovato")

    # Imposta l'articolo come pubblicato e aggiorna la data di pubblicazione
    article.published = True
    article.published_at = datetime.utcnow()

    try:
        article.save()
        flash('Articolo pubblicato con successo!', 'success')
    except Exception as e:
        flash(
            f'Errore durante la pubblicazione dell\'articolo: {str(e)}', 'danger')

    # Reindirizza alla stessa pagina da cui è stato effettuato l'accesso
    # (supponendo che sia una sorta di dashboard degli articoli).
    return redirect(request.referrer)


@app.route('/article/revise/<slug>', methods=['POST'])
@login_required
def revise_article(slug):
    article = Article.objects(slug=slug).first()

    if not article:
        abort(404, description="Articolo non trovato")

    # Imposta l'articolo come non pubblicato
    article.published = False

    # Se desideri resettare anche la data di pubblicazione, puoi farlo.
    # Altrimenti, commenta o rimuovi la riga seguente.
    article.published_at = None

    try:
        article.save()
        flash('Articolo messo in revisione con successo!', 'info')
    except Exception as e:
        flash(
            f'Errore durante la messa in revisione dell\'articolo: {str(e)}', 'danger')

    # Reindirizza alla stessa pagina da cui è stato effettuato l'accesso
    # (presumibilmente una sorta di dashboard degli articoli).
    return redirect(request.referrer)


@app.route('/search_pexels', methods=['POST'])
def search_pexels():
    query = request.form.get('query')
    try:
        response = requests.get(PEXELS_BASE_URL, params={'query': query}, headers={
                                'Authorization': PEXELS_API_KEY})
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/latest-articles-by-category/<int:page>')
def latest_articles_by_category(page=1):
    per_page = 10  # numero di articoli per pagina
    categories = Category.objects.all()

    data = []  # Lista che conterrà i dati da restituire

    for category in categories:
        # Recupera gli articoli per ogni categoria
        articles = Article.objects(category=category, published=True).order_by(
            '-published_at').skip((page-1)*per_page).limit(per_page)

        # Popola la lista data
        data.append({
            'category_name': category.name,
            'articles': [
                {
                    'title': a.title,
                    'intro': a.article_intro,
                    'slug': a.slug,
                    'main_photo': a.main_photo,
                    'published_at': a.published_at,
                    'video': {
                        # Assumendo che "video" sia un campo opzionale
                        'channel_icon_url': a.video.channel_icon_url if a.video else None,
                        # Assumendo che "video" sia un campo opzionale
                        'channel_title': a.video.channel_title if a.video else None
                    }
                } for a in articles
            ]
        })

    return jsonify(data)  # Restituisce i dati in formato JSON


@app.route('/category/<category_slug>')
def category_page(category_slug):
    category = Category.objects(slug=category_slug).first()
    if not category:
        abort(404)  # Se la categoria non esiste, mostra un errore 404

    articles = Article.objects(
        category=category, published=True).order_by('-published_at')
    return render_template('frontend/categories.html', category=category, articles=articles)


@app.route('/privacy-policy')
def privacy_policy():
    return render_template('frontend/privacy-policy.html')


# main
if __name__ == "__main__":
    app.run(debug=True)
