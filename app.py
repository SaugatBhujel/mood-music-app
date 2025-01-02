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
SPOTIPY_REDIRECT_URI = 'https://mood-music-app-uwtu.onrender.com/callback'  # Hardcoding to ensure exact match

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
        sp_oauth = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope='user-library-read playlist-modify-public user-top-read streaming user-read-email user-read-private'
        )
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        sp_oauth = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope='user-library-read playlist-modify-public user-top-read streaming user-read-email user-read-private'
        )
        
        code = request.args.get('code')
        
        # Get a fresh token
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        session['token_info'] = token_info
        
        return redirect('/')
        
    except Exception as e:
        return f"Error during authentication: {str(e)}"

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
        if 'token_info' not in session:
            return jsonify({'error': 'Please login first'}), 401

        token_info = session['token_info']
        sp = spotipy.Spotify(auth=token_info['access_token'])

        # Basic error check
        try:
            sp.current_user()
        except Exception as e:
            print(f"User check failed: {str(e)}")
            return jsonify({'error': 'Session expired. Please login again'}), 401

        data = request.get_json()
        mood = data.get('mood', '').lower() if data else None
        
        if not mood:
            return jsonify({'error': 'Please select a mood'}), 400

        # Get tracks from Spotify's Top 50 Global playlist
        try:
            playlist_tracks = sp.playlist_tracks('37i9dQZEVXbMDoHDwVN2tF', limit=50)
            if not playlist_tracks['items']:
                return jsonify({'error': 'Could not fetch playlist tracks'}), 500
                
            # Get track IDs from the playlist
            all_tracks = [item['track']['id'] for item in playlist_tracks['items'] if item['track']]
            
            # Take first track as seed
            seed_track = all_tracks[0] if all_tracks else None
            
            if not seed_track:
                return jsonify({'error': 'No valid tracks found in playlist'}), 500
                
        except Exception as e:
            print(f"Failed to get playlist tracks: {str(e)}")
            return jsonify({'error': 'Failed to get playlist tracks'}), 500

        # Get mood-specific parameters
        target_energy = {
            'happy': 0.8,
            'sad': 0.3,
            'energetic': 0.9,
            'calm': 0.3,
            'romantic': 0.5
        }.get(mood, 0.5)

        target_valence = {
            'happy': 0.8,
            'sad': 0.3,
            'energetic': 0.7,
            'calm': 0.5,
            'romantic': 0.6
        }.get(mood, 0.5)

        # Get recommendations using top track as seed
        try:
            recommendations = sp.recommendations(
                seed_tracks=[seed_track],
                limit=20,
                target_energy=target_energy,
                target_valence=target_valence,
                min_popularity=50
            )
        except Exception as e:
            print(f"Recommendation error: {str(e)}")
            return jsonify({'error': f'Failed to get recommendations: {str(e)}'}), 500

        if not recommendations['tracks']:
            return jsonify({'error': 'No tracks found. Please try again.'}), 404

        tracks = []
        for track in recommendations['tracks']:
            try:
                track_data = {
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown Artist',
                    'album': track['album']['name'] if track['album'] else 'Unknown Album',
                    'album_image': track['album']['images'][0]['url'] if track['album'].get('images') else None,
                    'preview_url': track['preview_url'],
                    'external_url': track['external_urls'].get('spotify', '')
                }
                tracks.append(track_data)
            except Exception as e:
                print(f"Error processing track: {str(e)}")
                continue

        if not tracks:
            return jsonify({'error': 'Failed to process tracks'}), 500

        return jsonify({'tracks': tracks, 'mood': mood})

    except Exception as e:
        print(f"General error: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

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
