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

def get_spotify():
    """Get Spotify client with fresh token"""
    try:
        if 'token_info' not in session:
            print("No token in session")
            return None

        token_info = session['token_info']

        # Check if token needs refresh
        now = int(time.time())
        is_expired = token_info['expires_at'] - now < 60

        if is_expired:
            print("Token expired, refreshing...")
            sp_oauth = SpotifyOAuth(
                client_id=SPOTIPY_CLIENT_ID,
                client_secret=SPOTIPY_CLIENT_SECRET,
                redirect_uri=SPOTIPY_REDIRECT_URI,
                scope='user-library-read playlist-modify-public user-top-read streaming user-read-email user-read-private'
            )
            token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
            session['token_info'] = token_info

        return spotipy.Spotify(auth=token_info['access_token'])

    except Exception as e:
        print(f"Error getting Spotify client: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

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
            scope='user-library-read playlist-modify-public user-top-read streaming user-read-email user-read-private',
            show_dialog=True  # Force showing the Spotify login dialog
        )
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    except Exception as e:
        print(f"Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
        if not code:
            print("No code in callback")
            return redirect('/')
            
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        if not token_info:
            print("Failed to get token info")
            return redirect('/')
            
        # Store token info in session
        session['token_info'] = token_info
        
        # Test the token
        try:
            sp = spotipy.Spotify(auth=token_info['access_token'])
            sp.current_user()
            print("Successfully authenticated user")
        except Exception as e:
            print(f"Token test failed: {str(e)}")
            session.pop('token_info', None)
            return redirect('/')
        
        return redirect('/')
        
    except Exception as e:
        print(f"Callback error: {str(e)}")
        return redirect('/')

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

@app.route('/api/get-recommendations', methods=['POST'])
def get_recommendations():
    try:
        if 'token_info' not in session:
            print("No token in session")
            return jsonify({'error': 'Please login first'}), 401

        token_info = session['token_info']
        if not token_info:
            print("Token info is empty")
            return jsonify({'error': 'Invalid session, please login again'}), 401

        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Verify the token works
        try:
            sp.current_user()
        except Exception as e:
            print(f"Token verification failed: {str(e)}")
            session.pop('token_info', None)
            return jsonify({'error': 'Session expired, please login again'}), 401

        data = request.get_json()
        if not data:
            print("No data in request")
            return jsonify({'error': 'No data provided'}), 400
            
        mood = data.get('mood', '').lower()
        if not mood:
            print("No mood specified")
            return jsonify({'error': 'Please select a mood'}), 400

        print(f"Processing request for mood: {mood}")

        # Map moods to specific popular playlists
        mood_to_playlist = {
            'happy': '37i9dQZF1DXdPec7aLTmlC',      # Happy Hits
            'sad': '37i9dQZF1DX7qK8ma5wgG1',        # Sad Songs
            'energetic': '37i9dQZF1DX76Wlfdnj7AP',  # Beast Mode
            'calm': '37i9dQZF1DWZd79rJ6a7lp',       # Sleep
            'romantic': '37i9dQZF1DX50QitC6Oqtn'    # Love Pop
        }

        playlist_id = mood_to_playlist.get(mood)
        if not playlist_id:
            print(f"Invalid mood selected: {mood}")
            return jsonify({'error': 'Invalid mood selected'}), 400

        print(f"Getting tracks from playlist: {playlist_id}")

        try:
            # Get tracks from the mood-specific playlist
            results = sp.playlist_tracks(
                playlist_id,
                fields='items(track(id,name,artists,album(name,images),preview_url,external_urls))',
                limit=20
            )
            
            if not results:
                print("No results from playlist")
                return jsonify({'error': 'Failed to get playlist'}), 500
                
            if 'items' not in results:
                print("No items in results")
                return jsonify({'error': 'No tracks in playlist'}), 404

            tracks = []
            for item in results['items']:
                if not item:
                    continue
                    
                if 'track' not in item:
                    continue
                    
                track = item['track']
                if not track:
                    continue

                try:
                    # Get track data
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
                    print(f"Added track: {track_data['name']}")
                except Exception as e:
                    print(f"Error processing track: {str(e)}")
                    continue

            if not tracks:
                print("No valid tracks found")
                return jsonify({'error': 'No valid tracks found'}), 404

            print(f"Successfully found {len(tracks)} tracks")
            return jsonify({
                'tracks': tracks,
                'mood': mood,
                'message': f'Found {len(tracks)} tracks for {mood} mood'
            })

        except spotipy.exceptions.SpotifyException as e:
            print(f"Spotify API error: {str(e)}")
            return jsonify({'error': f'Spotify API error: {str(e)}'}), 500
        except Exception as e:
            print(f"Error getting playlist tracks: {str(e)}")
            return jsonify({'error': 'Failed to get playlist tracks'}), 500

    except Exception as e:
        print(f"General error in get_recommendations: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/api/mood-based-recommendations', methods=['POST'])
def get_mood_recommendations():
    try:
        if 'token_info' not in session:
            print("No token in session")
            return jsonify({'error': 'Please login first'}), 401

        token_info = session['token_info']
        if not token_info:
            print("Token info is empty")
            return jsonify({'error': 'Invalid session, please login again'}), 401

        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Verify the token works
        try:
            sp.current_user()
        except Exception as e:
            print(f"Token verification failed: {str(e)}")
            session.pop('token_info', None)
            return jsonify({'error': 'Session expired, please login again'}), 401

        data = request.get_json()
        if not data or 'mood' not in data:
            return jsonify({'error': 'No mood provided'}), 400

        mood = data['mood'].lower()
        print(f"Getting recommendations for mood: {mood}")

        # First get some popular tracks based on mood
        mood_queries = {
            'happy': 'happy feel good',
            'sad': 'sad emotional',
            'energetic': 'party dance',
            'calm': 'relaxing calm',
            'romantic': 'love romantic'
        }

        if mood not in mood_queries:
            return jsonify({'error': 'Invalid mood'}), 400

        # Search for tracks matching the mood
        try:
            print(f"Searching for tracks with query: {mood_queries[mood]}")
            search_results = sp.search(
                q=mood_queries[mood],
                type='track',
                limit=5
            )
            
            if not search_results or 'tracks' not in search_results:
                print("No search results found")
                return jsonify({'error': 'No tracks found'}), 404

            # Get seed tracks from search results
            seed_tracks = [track['id'] for track in search_results['tracks']['items'][:2]]
            print(f"Using seed tracks: {seed_tracks}")

            # Get recommendations based on these tracks
            print("Getting recommendations based on seed tracks")
            recommendations = sp.recommendations(
                seed_tracks=seed_tracks,
                limit=20,
                target_valence=0.8 if mood == 'happy' else 0.2 if mood == 'sad' else 0.5,
                target_energy=0.8 if mood in ['happy', 'energetic'] else 0.2 if mood == 'calm' else 0.5
            )
            
            if not recommendations or 'tracks' not in recommendations:
                print("No recommendations found")
                return jsonify({'error': 'No recommendations found'}), 404

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
                    print(f"Found track: {track_data['name']} by {track_data['artist']}")
                except Exception as e:
                    print(f"Error processing track: {str(e)}")
                    continue

            return jsonify({
                'tracks': tracks,
                'message': f'Found {len(tracks)} tracks for {mood} mood'
            })

        except Exception as e:
            print(f"Error in recommendation process: {str(e)}")
            return jsonify({'error': f'Failed to get recommendations: {str(e)}'}), 500

    except Exception as e:
        print(f"General error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search_tracks():
    try:
        if 'token_info' not in session:
            print("No token in session")
            return jsonify({'error': 'Please login first'}), 401

        token_info = session['token_info']
        if not token_info:
            print("Token info is empty")
            return jsonify({'error': 'Invalid session, please login again'}), 401

        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Verify the token works
        try:
            sp.current_user()
        except Exception as e:
            print(f"Token verification failed: {str(e)}")
            session.pop('token_info', None)
            return jsonify({'error': 'Session expired, please login again'}), 401

        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'No search query provided'}), 400

        query = data['query']
        print(f"Searching for: {query}")

        # Search for tracks
        results = sp.search(q=query, type='track', limit=20)
        
        if not results or 'tracks' not in results:
            return jsonify({'error': 'No results found'}), 404

        tracks = []
        for track in results['tracks']['items']:
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
                print(f"Found track: {track_data['name']}")
            except Exception as e:
                print(f"Error processing track: {str(e)}")
                continue

        return jsonify({
            'tracks': tracks,
            'message': f'Found {len(tracks)} tracks'
        })

    except Exception as e:
        print(f"Search error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/create-playlist', methods=['POST'])
def create_playlist():
    try:
        if 'token_info' not in session:
            return jsonify({'error': 'Please login first'}), 401

        token_info = session['token_info']
        sp = spotipy.Spotify(auth=token_info['access_token'])

        data = request.get_json()
        if not data or 'name' not in data or 'tracks' not in data:
            return jsonify({'error': 'Missing playlist name or tracks'}), 400

        playlist_name = data['name']
        track_uris = data['tracks']

        if not track_uris:
            return jsonify({'error': 'No tracks selected'}), 400

        # Get user ID
        try:
            user = sp.current_user()
            user_id = user['id']
        except Exception as e:
            print(f"Failed to get user: {str(e)}")
            return jsonify({'error': 'Failed to get user info'}), 500

        # Create playlist
        try:
            playlist = sp.user_playlist_create(
                user=user_id,
                name=playlist_name,
                public=True,
                description=f'Created with Mood Music App'
            )
        except Exception as e:
            print(f"Failed to create playlist: {str(e)}")
            return jsonify({'error': 'Failed to create playlist'}), 500

        # Add tracks to playlist
        try:
            sp.playlist_add_items(playlist['id'], track_uris)
        except Exception as e:
            print(f"Failed to add tracks: {str(e)}")
            return jsonify({'error': 'Failed to add tracks to playlist'}), 500

        return jsonify({
            'success': True,
            'message': 'Playlist created successfully!',
            'playlist_url': playlist['external_urls']['spotify']
        })

    except Exception as e:
        print(f"Create playlist error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-playlist', methods=['POST'])
def save_playlist():
    try:
        sp = get_spotify()
        if not sp:
            return jsonify({'error': 'Please login first'}), 401

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

@app.route('/logout')
def logout():
    session.pop('token_info', None)
    return redirect('/')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
