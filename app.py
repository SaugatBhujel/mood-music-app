from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_session import Session
import os
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import logging
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from mood_detector import MoodDetector

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

mood_detector = MoodDetector()

def create_spotify():
    auth_manager = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope='playlist-modify-public playlist-modify-private user-read-private',
        cache_handler=None
    )
    return spotipy.Spotify(auth_manager=auth_manager)

@app.route('/')
def index():
    if not session.get('token_info'):
        return render_template('index.html', authenticated=False)
    try:
        sp = spotipy.Spotify(auth=session['token_info']['access_token'])
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

@app.route('/spotify-login')
def spotify_login():
    sp = create_spotify()
    auth_url = sp.auth_manager.get_authorize_url()
    logger.debug(f"Generated Spotify auth URL: {auth_url}")
    return redirect(auth_url)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        logger.debug(f"Login attempt for email: {email}")
        if email in users:
            logger.debug(f"User found: {email}")
            login_user(users[email])
            return redirect(url_for('profile'))
        else:
            logger.warning(f"User not found: {email}")
            # If user not found, create a new one
            users[email] = User(id=email)
            login_user(users[email])
            return redirect(url_for('profile'))
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
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-playlist', methods=['POST'])
def generate_playlist():
    try:
        if 'token_info' not in session:
            return jsonify({'error': 'Not authenticated with Spotify'}), 401

        data = request.get_json()
        mood = data.get('mood', '')
        city = data.get('city', None)
        
        # Get enhanced mood suggestions
        suggested_moods = mood_detector.combine_moods(mood, city)
        primary_mood = suggested_moods[0]
        
        # Create Spotify client with stored token
        sp = spotipy.Spotify(auth=session['token_info']['access_token'])
        
        # Get recommendations based on mood
        seed_genres = get_genres_for_mood(primary_mood)[:5]  # Limit to 5 genres
        
        logger.debug(f"Using seed genres: {seed_genres}")
        
        try:
            recommendations = sp.recommendations(
                seed_genres=seed_genres,
                limit=20,
                target_energy=get_energy_for_mood(primary_mood),
                target_valence=get_valence_for_mood(primary_mood)
            )
        except Exception as e:
            logger.error(f"Error getting recommendations: {str(e)}")
            # Fallback to simpler genres if the first attempt fails
            fallback_genres = ['pop', 'rock']
            recommendations = sp.recommendations(
                seed_genres=fallback_genres,
                limit=20,
                target_energy=0.5,
                target_valence=0.5
            )
        
        # Create playlist
        tracks = [track['uri'] for track in recommendations['tracks']]
        playlist_name = f"{primary_mood} Mood - {datetime.now().strftime('%Y-%m-%d')}"
        
        user_id = sp.current_user()['id']
        playlist = sp.user_playlist_create(user_id, playlist_name, public=False)
        
        if tracks:
            sp.playlist_add_items(playlist['id'], tracks)
        
        return jsonify({
            'playlist_id': playlist['id'],
            'playlist_url': playlist['external_urls']['spotify'],
            'suggested_moods': suggested_moods
        })
        
    except Exception as e:
        logger.error(f"Error generating playlist: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_genres_for_mood(mood):
    """Map moods to appropriate genres"""
    mood_genres = {
        'Happy': ['pop', 'dance', 'disco'],
        'Energetic': ['dance', 'electronic', 'house'],
        'Peaceful': ['classical', 'ambient', 'study'],
        'Melancholic': ['indie', 'acoustic', 'piano'],
        'Relaxed': ['jazz', 'acoustic', 'ambient'],
        'Focused': ['classical', 'electronic', 'study'],
        'Mellow': ['indie', 'folk', 'acoustic'],
        'Romantic': ['jazz', 'soul', 'r-n-b'],
        'Night': ['chill', 'electronic', 'study'],
        'Morning': ['pop', 'indie', 'dance']
    }
    return mood_genres.get(mood, ['pop', 'rock'])

def get_energy_for_mood(mood):
    """Map moods to energy levels (0.0 to 1.0)"""
    energy_levels = {
        'Happy': 0.8,
        'Energetic': 0.9,
        'Peaceful': 0.3,
        'Melancholic': 0.4,
        'Relaxed': 0.3,
        'Focused': 0.5,
        'Mellow': 0.4,
        'Romantic': 0.5,
        'Night': 0.2,
        'Morning': 0.7
    }
    return energy_levels.get(mood, 0.6)

def get_valence_for_mood(mood):
    """Map moods to valence/positivity levels (0.0 to 1.0)"""
    valence_levels = {
        'Happy': 0.8,
        'Energetic': 0.7,
        'Peaceful': 0.6,
        'Melancholic': 0.3,
        'Relaxed': 0.5,
        'Focused': 0.6,
        'Mellow': 0.5,
        'Romantic': 0.6,
        'Night': 0.4,
        'Morning': 0.7
    }
    return valence_levels.get(mood, 0.5)

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
