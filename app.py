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
import time

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
    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope='playlist-modify-public playlist-modify-private user-read-private',
            cache_handler=None
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        logger.error(f"Error creating Spotify client: {str(e)}")
        return None

@app.route('/')
def index():
    try:
        if not all([SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI]):
            logger.error("Missing Spotify credentials")
            return render_template('index.html', error="Spotify configuration is incomplete")
        if not session.get('token_info'):
            return render_template('index.html', authenticated=False)
        try:
            sp = spotipy.Spotify(auth=session['token_info']['access_token'])
            sp.current_user()
            return render_template('index.html', authenticated=True)
        except:
            return render_template('index.html', authenticated=False)
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        return render_template('index.html', error="An unexpected error occurred")

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
    try:
        logger.debug("Starting Spotify login process")
        sp = create_spotify()
        if not sp:
            logger.error("Failed to create Spotify client")
            return jsonify({'error': 'Failed to initialize Spotify client'}), 500
            
        auth_url = sp.auth_manager.get_authorize_url()
        logger.debug(f"Generated Spotify auth URL: {auth_url}")
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"Error in Spotify login: {str(e)}")
        return jsonify({'error': 'Failed to initialize Spotify login'}), 500

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
        logger.debug("Received Spotify callback")
        sp = create_spotify()
        if not sp:
            logger.error("Failed to create Spotify client in callback")
            return redirect(url_for('index', error='Failed to initialize Spotify client'))

        code = request.args.get('code')
        if not code:
            logger.error("No code in callback")
            return redirect(url_for('index', error='Authentication failed'))

        token_info = sp.auth_manager.get_access_token(code)
        session['token_info'] = token_info
        logger.debug("Successfully got token info")
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}")
        return redirect(url_for('index', error=str(e)))

def get_energy_for_mood(mood):
    """Map moods to energy levels (0.0 to 1.0)"""
    mood_energy = {
        'happy': 0.8,
        'sad': 0.3,
        'energetic': 0.9,
        'calm': 0.2,
        'romantic': 0.5
    }
    return mood_energy.get(mood.lower(), 0.5)

def get_valence_for_mood(mood):
    """Map moods to valence/positivity levels (0.0 to 1.0)"""
    mood_valence = {
        'happy': 0.8,
        'sad': 0.2,
        'energetic': 0.7,
        'calm': 0.5,
        'romantic': 0.6
    }
    return mood_valence.get(mood.lower(), 0.5)

def get_genres_for_mood(mood):
    """Map moods to Spotify genres"""
    mood_genres = {
        'happy': ['pop'],
        'sad': ['acoustic'],
        'energetic': ['dance'],
        'calm': ['classical'],
        'romantic': ['jazz']
    }
    return mood_genres.get(mood.lower(), ['pop'])

@app.route('/api/get-recommendations', methods=['POST'])
def get_recommendations():
    try:
        logger.debug("=== Starting recommendation request ===")
        
        if 'token_info' not in session:
            logger.error("No token_info in session")
            return jsonify({'error': 'Please login with Spotify first'}), 401

        # Get and refresh token if needed
        try:
            sp_oauth = SpotifyOAuth(
                client_id=SPOTIPY_CLIENT_ID,
                client_secret=SPOTIPY_CLIENT_SECRET,
                redirect_uri=SPOTIPY_REDIRECT_URI,
                scope='user-library-read playlist-modify-public user-top-read',
                cache_handler=None
            )
            
            token_info = session.get('token_info', {})
            if sp_oauth.is_token_expired(token_info):
                token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
                session['token_info'] = token_info
                logger.debug("Token refreshed")
                
            sp = spotipy.Spotify(auth=token_info['access_token'])
        except Exception as e:
            logger.error(f"Error with Spotify auth: {str(e)}")
            return jsonify({'error': 'Failed to authenticate with Spotify. Please login again.'}), 401

        # Get the mood from request
        data = request.get_json()
        if not data:
            logger.error("No JSON data in request")
            return jsonify({'error': 'No data provided'}), 400
            
        mood = data.get('mood', '').lower()
        if not mood:
            logger.error("No mood specified")
            return jsonify({'error': 'Please specify a mood'}), 400
        
        logger.debug(f"Processing mood: {mood}")
        
        try:
            # Test the Spotify connection
            user = sp.current_user()
            logger.debug(f"Spotify connection test successful. User: {user['id']}")
            
            # Get available genres from Spotify
            available_genres = sp.recommendation_genre_seeds()
            logger.debug(f"Available genres: {available_genres}")
            
            # Get recommendations based on genres
            recommendations = sp.recommendations(
                seed_genres=['pop'],  # Start with pop as a safe genre
                limit=20,
                target_energy=get_energy_for_mood(mood),
                target_valence=get_valence_for_mood(mood)
            )
            
            logger.debug(f"Got {len(recommendations['tracks'])} recommendations")
            
            # Format track information for frontend
            tracks = []
            for track in recommendations['tracks']:
                track_data = {
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'],
                    'album_image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'uri': track['uri'],
                    'preview_url': track['preview_url'],
                    'external_url': track['external_urls']['spotify']
                }
                tracks.append(track_data)
                logger.debug(f"Added track: {track['name']} by {track['artists'][0]['name']}")
            
            if not tracks:
                logger.error("No tracks were found")
                return jsonify({'error': 'No tracks found for this mood. Please try a different mood.'}), 404
            
            response_data = {
                'tracks': tracks,
                'mood': mood
            }
            logger.debug(f"=== Finished processing. Returning {len(tracks)} tracks ===")
            return jsonify(response_data)
            
        except spotipy.exceptions.SpotifyException as e:
            logger.error(f"Spotify API error: {str(e)}")
            return jsonify({'error': f'Spotify API error: {str(e)}'}), 401
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/api/create-playlist', methods=['POST'])
def create_playlist():
    try:
        if 'token_info' not in session:
            return jsonify({'error': 'Not authenticated with Spotify'}), 401

        data = request.get_json()
        selected_tracks = data.get('tracks', [])
        mood = data.get('mood', 'Custom')
        
        if not selected_tracks:
            return jsonify({'error': 'No tracks selected'}), 400
        
        sp = spotipy.Spotify(auth=session['token_info']['access_token'])
        
        # Create playlist
        playlist_name = f"{mood} Mood - {datetime.now().strftime('%Y-%m-%d')}"
        user_id = sp.current_user()['id']
        playlist = sp.user_playlist_create(user_id, playlist_name, public=False)
        
        # Add selected tracks to playlist
        sp.playlist_add_items(playlist['id'], selected_tracks)
        
        return jsonify({
            'playlist_id': playlist['id'],
            'playlist_url': playlist['external_urls']['spotify']
        })
        
    except Exception as e:
        logger.error(f"Error creating playlist: {str(e)}")
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
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
