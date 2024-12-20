document.addEventListener('DOMContentLoaded', () => {
    const moodButtons = document.querySelectorAll('.mood-btn');
    const playlistContainer = document.querySelector('.playlist-container');
    const playlistContent = document.querySelector('.playlist-content');
    const savePlaylistBtn = document.querySelector('.save-playlist');
    const savedPlaylistsContent = document.querySelector('.saved-playlists-content');

    // Mood color mapping
    const moodColors = {
        happy: '#FFF8DC',
        sad: '#F0F8FF',
        energetic: '#FFF0F5',
        calm: '#F0FFF0'
    };

    let currentPlaylist = null;

    // Handle mood selection
    moodButtons.forEach(button => {
        button.addEventListener('click', async () => {
            const mood = button.dataset.mood;
            
            // Update background color based on mood
            document.body.style.backgroundColor = moodColors[mood];
            
            // Show loading state
            playlistContent.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div><p>Generating your playlist...</p></div>';
            playlistContainer.style.display = 'block';
            
            // Generate playlist
            try {
                const response = await fetch('/api/generate-playlist', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ mood })
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to generate playlist');
                }
                
                const playlist = await response.json();
                currentPlaylist = playlist;
                
                // Display playlist
                displayPlaylist(playlist);
                
            } catch (error) {
                console.error('Error generating playlist:', error);
                playlistContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <h4 class="alert-heading">Error</h4>
                        <p>${error.message}</p>
                        <hr>
                        <p class="mb-0">Please try again or try a different mood.</p>
                    </div>
                `;
            }
        });
    });

    // Display playlist function
    function displayPlaylist(playlist) {
        playlistContent.innerHTML = playlist.songs.map(song => `
            <div class="song-item">
                ${song.image ? `
                    <div class="song-image">
                        <img src="${song.image}" alt="${song.title}" class="img-fluid rounded">
                    </div>
                ` : ''}
                <div class="song-info">
                    <div class="song-title">${song.title}</div>
                    <div class="song-artist">${song.artist}</div>
                </div>
                <div class="song-actions">
                    ${song.preview_url ? `
                        <button class="btn btn-sm btn-outline-secondary preview-btn" data-preview-url="${song.preview_url}">
                            <i class="fas fa-play"></i>
                        </button>
                    ` : ''}
                    <a href="${song.link}" target="_blank" class="btn btn-sm btn-success">
                        <i class="fab fa-spotify"></i>
                    </a>
                </div>
            </div>
        `).join('');

        // Add preview functionality
        const previewButtons = document.querySelectorAll('.preview-btn');
        let currentAudio = null;

        previewButtons.forEach(button => {
            button.addEventListener('click', () => {
                const previewUrl = button.dataset.previewUrl;
                
                if (currentAudio) {
                    currentAudio.pause();
                    currentAudio = null;
                    document.querySelector('.preview-btn.playing')?.classList.remove('playing');
                }

                if (button.classList.contains('playing')) {
                    button.classList.remove('playing');
                } else {
                    currentAudio = new Audio(previewUrl);
                    currentAudio.play();
                    button.classList.add('playing');
                    
                    currentAudio.addEventListener('ended', () => {
                        button.classList.remove('playing');
                        currentAudio = null;
                    });
                }
            });
        });
    }

    // Save playlist
    function savePlaylist() {
        if (currentPlaylist) {
            fetch('/api/save-playlist', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(currentPlaylist)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert('Playlist saved to your Spotify account! Check your Spotify app.');
                    loadSavedPlaylists();  // Refresh the saved playlists
                } else {
                    alert('Error saving playlist: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error saving playlist');
            });
        }
    }

    savePlaylistBtn.addEventListener('click', savePlaylist);

    // Show toast notification
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type === 'error' ? 'bg-danger' : 'bg-success'} text-white position-fixed bottom-0 end-0 m-3`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="toast-body">
                ${message}
            </div>
        `;
        document.body.appendChild(toast);
        
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
        
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }

    // Load saved playlists
    async function loadSavedPlaylists() {
        try {
            const response = await fetch('/api/saved-playlists');
            const playlists = await response.json();
            
            savedPlaylistsContent.innerHTML = playlists.map(playlist => `
                <div class="saved-playlist-item card mb-3">
                    <div class="card-body">
                        <h5 class="card-title">${playlist.mood.charAt(0).toUpperCase() + playlist.mood.slice(1)} Playlist</h5>
                        <p class="card-text">
                            <small class="text-muted">Created: ${new Date(playlist.timestamp).toLocaleDateString()}</small>
                        </p>
                        <div class="song-list">
                            ${playlist.songs.slice(0, 3).map(song => `
                                <div class="small">${song.title} - ${song.artist}</div>
                            `).join('')}
                            ${playlist.songs.length > 3 ? `<div class="small text-muted">+ ${playlist.songs.length - 3} more songs</div>` : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('Error loading saved playlists:', error);
        }
    }

    // Initial load of saved playlists
    loadSavedPlaylists();
});
