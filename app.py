from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_session import Session
import os
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import logging
import random
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')  # Use environment variable or fallback
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Specify the login view

# User model
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# In-memory user store (for demonstration)
users = {'user@example.com': User(id='user@example.com')}

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

# Spotify Configuration
SPOTIPY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

# Simple mood configurations for speed
MOOD_CONFIGS = {
    'happy': 'genre:pop mood:happy',
    'sad': 'genre:ballad',  # Simplified to just ballads which are typically sad
    'energetic': 'genre:dance mood:party',
    'calm': 'genre:ambient mood:peaceful'
}

def create_spotify():
    auth_manager = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope='user-library-read playlist-modify-public user-read-private',
        cache_path=None
    )
    return spotipy.Spotify(auth_manager=auth_manager)

@app.route('/')
def index():
    if not session.get('token_info'):
        return render_template('index.html', authenticated=False)
    try:
        sp = create_spotify()
        sp.current_user()
        return render_template('index.html', authenticated=True)
    except:
        return render_template('index.html', authenticated=False)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        # Here you would save the user to a database
        users[email] = User(id=email)
        login_user(users[email])
        return redirect(url_for('profile'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        logger.debug(f"Login attempt for email: {email}")  # Log the email being processed
        if email in users:
            logger.debug(f"User found: {email}")  # Log if user is found
            login_user(users[email])
            return redirect(url_for('profile'))
        else:
            logger.warning(f"User not found: {email}")  # Log if user is not found
    return render_template('login.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/callback')
def callback():
    try:
        sp = create_spotify()
        code = request.args.get('code')
        token_info = sp.auth_manager.get_access_token(code)
        session['token_info'] = token_info
        logger.debug("Successfully got token info")
        return redirect('/')
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-playlist', methods=['POST'])
def generate_playlist():
    try:
        sp = create_spotify()
        mood = request.json.get('mood', 'happy')
        
        if mood not in MOOD_CONFIGS:
            return jsonify({'error': 'Invalid mood'}), 400
            
        search_query = MOOD_CONFIGS[mood]
        offset = random.randint(0, 20)  # Small offset for speed
        
        results = sp.search(
            q=search_query,
            type='track',
            limit=10,  # Just get what we need
            offset=offset
        )
        
        if not results or 'tracks' not in results or not results['tracks']['items']:
            return jsonify({'error': 'No tracks found'}), 404
            
        tracks = results['tracks']['items']
        random.shuffle(tracks)  # Shuffle for variety
        
        playlist = {
            'mood': mood,
            'songs': [{
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'link': track['external_urls']['spotify'],
                'preview_url': track['preview_url'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None
            } for track in tracks]
        }
        
        return jsonify(playlist)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-playlist', methods=['POST'])
def save_playlist():
    try:
        sp = create_spotify()
        user = sp.current_user()
        user_id = user['id']
        
        playlist_data = request.json
        mood = playlist_data.get('mood', 'Unknown Mood')
        songs = playlist_data.get('songs', [])
        
        # Create a new playlist in Spotify
        playlist_name = f"{mood.capitalize()} Mood - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        playlist = sp.user_playlist_create(user_id, playlist_name, public=True)
        
        # Get track URIs
        track_uris = []
        for song in songs:
            # Extract track ID from the Spotify link
            track_id = song['link'].split('/')[-1]
            track_uris.append(f"spotify:track:{track_id}")
        
        # Add tracks to the playlist
        if track_uris:
            sp.playlist_add_items(playlist['id'], track_uris)
        
        # Also save to session for local reference
        if 'playlists' not in session:
            session['playlists'] = []
        playlist_data['timestamp'] = datetime.now().isoformat()
        playlist_data['spotify_url'] = playlist['external_urls']['spotify']
        session['playlists'].append(playlist_data)
        
        return jsonify({
            'status': 'success',
            'message': 'Playlist saved to Spotify!',
            'spotify_url': playlist['external_urls']['spotify']
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/saved-playlists')
def get_saved_playlists():
    return jsonify(session.get('playlists', []))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
