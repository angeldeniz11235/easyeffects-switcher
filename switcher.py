#!/usr/bin/env python3
import os
import json
import re
import urllib.request
import urllib.parse
import subprocess
import logging
import dbus
import threading
import time
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_FILE = os.path.join(BASE_DIR, "mappings.json")
CACHE_FILE = os.path.join(BASE_DIR, "cache.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")
AGY_PATH = "/home/wh0/.local/bin/agy"


# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Genre to EasyEffects preset mapping for Music
GENRE_TO_PRESET = {
    # Country / Americana / Folk
    "country": "country.v1",
    "americana": "country.v1",
    "folk": "country.v1",
    "bluegrass": "country.v1",
    
    # Rock / Metal / Punk
    "rock": "rock-max",
    "metal": "rock-max",
    "grunge": "rock-max",
    "punk": "rock-max",
    "alternative rock": "rock-max",
    "hard rock": "rock-max",
    
    # Electronic / EDM / Dance / Techno / House
    "electronic": "edm-max",
    "edm": "edm-max",
    "techno": "edm-max",
    "house": "edm-max",
    "trance": "edm-max",
    "synthpop": "edm-max",
    "synthwave": "edm-max",
    "industrial": "edm-max",
    "dance": "edm-max",
    
    # Classical / Ambient / Instrumental
    "classical": "classical-min",
    "orchestral": "classical-min",
    "ambient": "classical-min",
    "soundtrack": "classical-min",
    "instrumental": "classical-min",
    
    # Indie / Alternative
    "indie": "indie-max",
    "indie rock": "indie-max",
    "indie pop": "indie-max",
    "alternative": "indie-max",
    
    # K-Pop / J-Pop
    "k-pop": "kpop-max",
    "kpop": "kpop-max",
    "j-pop": "kpop-max",
    "jpop": "kpop-max",
    
    # Lo-fi / Chill
    "lofi": "lofi-max",
    "lo-fi": "lofi-max",
    "chillhop": "lofi-max",
    "downtempo": "lofi-max",
    
    # Pop / Hip Hop / Soul / R&B
    "pop": "Bose",
    "hip hop": "Bose",
    "rap": "Bose",
    "soul": "Bose",
    "r&b": "Bose",
    "rhythm and blues": "Bose",
}

DEFAULT_PRESET = "YouTube-1"

# Movie Genre to EasyEffects preset mapping
MOVIE_GENRE_TO_PRESET = {
    "action": "movie-action",
    "sci-fi": "movie-action",
    "drama": "movie-drama",
    "horror": "movie-horror",
    "musical": "movie-musical",
    "comedy": "movie-standard",
    "documentary": "movie-standard",
    "animation": "movie-standard",
}

DEFAULT_MOVIE_PRESET = "movie-standard"

# Global states
players_state = {}
sender_cache = {}
active_player = None
player_request_ids = {}
last_applied_preset = None
last_active_media = None


def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading {filepath}: {e}")
        return default

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving {filepath}: {e}")

def save_status(player_name, metadata, preset_name, playback_status, media_type=None):
    title = str(metadata.get("xesam:title", "")) if metadata else ""
    album = str(metadata.get("xesam:album", "")) if metadata else ""
    artists_dbus = metadata.get("xesam:artist", []) if metadata else []
    artists = [str(a) for a in artists_dbus]
    artist = ", ".join(artists) if artists else ""
    url = str(metadata.get("xesam:url", "")) if metadata else ""
    
    status_data = {
        "player": player_name if player_name else "",
        "playback_status": playback_status,
        "title": title,
        "artist": artist,
        "album": album,
        "url": url,
        "preset": preset_name if preset_name else "",
        "media_type": media_type if media_type else "",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json(STATUS_FILE, status_data)

def get_mapping_override(artist, album, title):
    mappings = load_json(MAPPINGS_FILE, {"artists": {}, "albums": {}, "titles": {}})
    
    # 1. Match Title
    if title and title.lower() in mappings.get("titles", {}):
        return mappings["titles"][title.lower()]
        
    # 2. Match Album
    if album and album.lower() in mappings.get("albums", {}):
        return mappings["albums"][album.lower()]
        
    # 3. Match Artist
    if artist and artist.lower() in mappings.get("artists", {}):
        return mappings["artists"][artist.lower()]
        
    return None

def is_video_player(player_name):
    # Any player other than spotify is considered a video/movie player in this setup
    return player_name.lower() != "spotify"

def clean_video_title(raw_title):
    title = raw_title
    # If the title is a file path or URL, get the basename
    if "/" in title:
        title = title.split("/")[-1]
    
    # Strip URL encoding if any
    title = urllib.parse.unquote(title)
    
    # Strip file extensions
    title = re.sub(r"\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v)$", "", title, flags=re.IGNORECASE)
    
    # Replace dots, underscores, and dashes with spaces
    title = re.sub(r"[\._\-]", " ", title)
    
    # Strip common scene tags, release groups, and quality info
    tags = [
        r"\b\d{3,4}p\b",  # 1080p, 720p, 2160p, etc.
        r"\b[hH]\.?26[45]\b", # h264, h265, x264, x265
        r"\b[hH]e[vV]c\b", # HEVC
        r"\b[bB]lu[rR]ay\b", # BluRay, Bluray
        r"\b[bB][dD][rR]ip\b",
        r"\b[wW][eE][bB]\-?[dD][lL]\b",
        r"\b[hH][dD][tT][vV]\b",
        r"\b[dD][dD][pP]\d\.\d\b", # DDP5.1, etc.
        r"\b[aA][aA][cC]\b",
        r"\b[dD][tT][sS]\b",
        r"\b[aA][cC]3\b",
        r"\b[yY][tT][sS]\b",
        r"\b[yY]i[fF][yY]\b",
        r"\b[xX]vi[dD]\b",
    ]
    for tag in tags:
        title = re.sub(tag, "", title, flags=re.IGNORECASE)
        
    # Clean up multiple spaces and leading/trailing whitespace
    title = re.sub(r"\s+", " ", title).strip()
    return title

def query_llm_for_movie_genre(cleaned_title):
    prompt = f"""Analyze the movie or show title '{cleaned_title}' and classify its primary genre.
Choose from: action, drama, horror, musical, comedy, sci-fi, documentary, animation.
Reply with ONLY the matching lowercase genre name from the list above. No other text, punctuation, or formatting."""
    
    try:
        logging.info(f"Querying LLM for movie genre of: '{cleaned_title}'")
        cmd = [AGY_PATH, "--print", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        genre = result.stdout.strip().lower()
        allowed_genres = {"action", "drama", "horror", "musical", "comedy", "sci-fi", "documentary", "animation"}
        for g in allowed_genres:
            if g in genre:
                return g
        logging.warning(f"LLM returned unrecognized movie genre: '{genre}'")
        return None
    except Exception as e:
        logging.error(f"Error querying LLM for movie genre: {e}")
        return None

def query_llm_for_music_genre(artist_name):
    prompt = f"""What is the primary music genre of the artist '{artist_name}'?
Choose from: country, rock, electronic, classical, indie, k-pop, lo-fi, pop, hip hop.
Reply with ONLY the matching lowercase genre name from the list above. No other text, punctuation, or formatting."""

    try:
        logging.info(f"Querying LLM for music genre of artist: '{artist_name}'")
        cmd = [AGY_PATH, "--print", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        genre = result.stdout.strip().lower()
        allowed_genres = {"country", "rock", "electronic", "classical", "indie", "k-pop", "lo-fi", "pop", "hip hop"}
        for g in allowed_genres:
            if g in genre:
                return g
        logging.warning(f"LLM returned unrecognized music genre: '{genre}'")
        return None
    except Exception as e:
        logging.error(f"Error querying LLM for music genre: {e}")
        return None

def is_browser_player(player_name):
    name_lower = player_name.lower()
    browsers = ["firefox", "chrome", "chromium", "brave", "vivaldi", "opera", "edge"]
    return any(b in name_lower for b in browsers)

def get_browser_media_type_by_url(url):
    if not url:
        return None
    url_lower = url.lower()
    
    # Music domains
    music_domains = [
        "music.youtube.com",
        "open.spotify.com",
        "soundcloud.com",
        "bandcamp.com",
        "pandora.com",
        "deezer.com",
        "tidal.com",
        "apple.com/apple-music"
    ]
    for domain in music_domains:
        if domain in url_lower:
            return "music"
            
    # Movie / Video domains
    movie_domains = [
        "netflix.com",
        "hulu.com",
        "disneyplus.com",
        "primevideo.com",
        "plex.tv",
        "hbo.com",
        "max.com",
        "peacocktv.com"
    ]
    for domain in movie_domains:
        if domain in url_lower:
            return "movie"
            
    return None

def query_llm_for_browser_media_type(title, artist, album, url):
    prompt = f"""Analyze the media metadata being played in a web browser:
- Title: "{title}"
- Creator/Artist: "{artist}"
- Album/Context: "{album}"
- Source/URL: "{url}"

Classify the primary content type of this media into exactly one of these three categories:
1. talk - for podcasts, lectures, tutorials, audiobooks, news, speeches, talks, interviews, and speech-dominant content.
2. music - for songs, music videos, instrumentals, or music-dominant content.
3. movie - for movies, TV shows, cinematic videos, movie trailers, or narrative fiction/entertainment videos.

Reply with ONLY the matching category name: talk, music, or movie. Do not include any other words, punctuation, formatting, or explanation."""

    try:
        logging.info(f"Querying LLM to classify browser media: '{title}' by '{artist}' (URL: '{url}')")
        cmd = [AGY_PATH, "--print", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        category = result.stdout.strip().lower()
        if "talk" in category:
            return "talk"
        elif "music" in category:
            return "music"
        elif "movie" in category:
            return "movie"
        logging.warning(f"LLM returned unrecognized media category: '{category}'")
        return None
    except Exception as e:
        logging.error(f"Error querying LLM for browser media classification: {e}")
        return None

def clean_browser_title(title):
    # Remove common site suffixes from page titles
    suffixes = [
        r"\s*-\s*YouTube\s*$",
        r"\s*-\s*Netflix\s*$",
        r"\s*-\s*Twitch\s*$",
        r"\s*-\s*Spotify\s*$",
        r"\s*-\s*SoundCloud\s*$",
        r"\s*-\s*Pandora\s*$",
        r"\s*-\s*Vimeo\s*$",
    ]
    cleaned = title
    for suffix in suffixes:
        cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE)
    return cleaned


def fetch_genre_from_musicbrainz(artist_name):
    # Check cache first
    cache = load_json(CACHE_FILE, {})
    if artist_name.lower() in cache:
        logging.info(f"Cache hit for artist: {artist_name}")
        return cache[artist_name.lower()]

    logging.info(f"Cache miss. Querying MusicBrainz for artist: {artist_name}")
    try:
        query = urllib.parse.quote(f"artist:{artist_name}")
        url = f"https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json"
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "EasyEffectsSwitcher/1.0.0 (contact: wh0@example.com)"}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode())
            
        artists = res_data.get("artists", [])
        if not artists:
            logging.warning(f"No artists found on MusicBrainz for query: {artist_name}")
            return None

        best_artist = artists[0]
        tags = best_artist.get("tags", [])
        tags_sorted = sorted(tags, key=lambda x: x.get("count", 0), reverse=True)
        tag_names = [t.get("name", "").lower() for t in tags_sorted]
        
        matched_preset = None
        for tag in tag_names:
            if tag in GENRE_TO_PRESET:
                matched_preset = GENRE_TO_PRESET[tag]
                logging.info(f"Matched tag '{tag}' to preset '{matched_preset}'")
                break
            for keyword, preset in GENRE_TO_PRESET.items():
                if keyword in tag:
                    matched_preset = preset
                    logging.info(f"Matched substring '{keyword}' in tag '{tag}' to preset '{matched_preset}'")
                    break
            if matched_preset:
                break
                
        if matched_preset:
            cache[artist_name.lower()] = matched_preset
            save_json(CACHE_FILE, cache)
        
        return matched_preset

    except Exception as e:
        logging.error(f"Error querying MusicBrainz: {e}")
        return None

def get_music_genre_preset(artist_name):
    # 1. Try MusicBrainz
    preset = fetch_genre_from_musicbrainz(artist_name)
    if preset:
        return preset
    
    # 2. Try LLM fallback
    logging.info(f"MusicBrainz lookup failed or returned no preset. Attempting LLM lookup for artist: {artist_name}")
    genre = query_llm_for_music_genre(artist_name)
    if genre and genre in GENRE_TO_PRESET:
        preset = GENRE_TO_PRESET[genre]
        # Cache this mapping in cache.json so we don't query the LLM again
        try:
            cache = load_json(CACHE_FILE, {})
            cache[artist_name.lower()] = preset
            save_json(CACHE_FILE, cache)
        except Exception as e:
            logging.error(f"Failed to cache LLM result: {e}")
        return preset

    return None

def get_media_identifier(player_name, metadata):
    if not metadata:
        return (player_name, "", "", "")
    track_id = metadata.get("mpris:trackid", "")
    title = metadata.get("xesam:title", "")
    url = metadata.get("xesam:url", "")
    return (player_name, str(track_id), str(title), str(url))

def apply_easyeffects_preset(preset_name):
    global last_applied_preset
    if last_applied_preset == preset_name:
        logging.info(f"EasyEffects preset is already set to '{preset_name}'. Skipping application.")
        return
    try:
        logging.info(f"Switching EasyEffects preset to: {preset_name}")
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        subprocess.run(
            ["flatpak", "run", "com.github.wwmm.easyeffects", "-l", preset_name],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        last_applied_preset = preset_name
    except Exception as e:
        logging.error(f"Failed to apply EasyEffects preset: {e}")


def process_player_change_async(player_name, metadata, req_id):
    title = str(metadata.get("xesam:title", ""))
    album = str(metadata.get("xesam:album", ""))
    artists_dbus = metadata.get("xesam:artist", [])
    artists = [str(a) for a in artists_dbus]
    artist = ", ".join(artists) if artists else ""
    url = str(metadata.get("xesam:url", ""))
    
    if not title and not artist:
        return
        
    preset = None
    media_type = None
    
    if is_browser_player(player_name):
        title = clean_browser_title(title)
        logging.info(f"Processing browser player '{player_name}': {title} (Req: {req_id})")
        
        # 1. First check if we can determine the type from URL
        media_type = get_browser_media_type_by_url(url)
        
        # 2. If URL classification is inconclusive, query the LLM
        if not media_type:
            if req_id != player_request_ids.get(player_name) or player_name != active_player:
                logging.info(f"Request {req_id} for '{player_name}' is obsolete. Skipping LLM browser media classification.")
                return
            media_type = query_llm_for_browser_media_type(title, artist, album, url)
            
        # Verify if this is still the active request
        if req_id != player_request_ids.get(player_name) or player_name != active_player:
            logging.info(f"Request {req_id} for '{player_name}' is obsolete. Discarding browser media type '{media_type}'.")
            return
            
        logging.info(f"Classified browser media as: '{media_type}'")
        
        if media_type == "talk":
            logging.info("Applying talk preset for browser speech/podcast content.")
            preset = "talk"
            
        elif media_type == "music":
            logging.info(f"Resolving music preset for browser music: '{title}' by '{artist}'")
            # 1. Check override mapping
            preset = get_mapping_override(artist, album, title)
            if not preset:
                # 2. Lookup/Fetch genre-based preset (MusicBrainz + LLM fallback)
                if req_id != player_request_ids.get(player_name) or player_name != active_player:
                    logging.info(f"Request {req_id} for '{player_name}' is obsolete. Skipping music genre lookup.")
                    return
                preset = get_music_genre_preset(artist)
                
                # Verify if this is still the active request
                if req_id != player_request_ids.get(player_name) or player_name != active_player:
                    logging.info(f"Request {req_id} for '{player_name}' is obsolete. Discarding preset '{preset}'.")
                    return
                    
                if not preset:
                    logging.info(f"No specific preset matched. Falling back to default: {DEFAULT_PRESET}")
                    preset = DEFAULT_PRESET
                
        elif media_type == "movie":
            logging.info(f"Resolving movie preset for browser video: '{title}'")
            cleaned_title = clean_video_title(title)
            logging.info(f"Cleaned browser video title: '{cleaned_title}'")
            
            # 1. Check override mapping (using cleaned title and raw title)
            preset = get_mapping_override(None, None, cleaned_title)
            if not preset:
                preset = get_mapping_override(None, None, title)
                
            if not preset:
                # 2. Query LLM to get genre
                if req_id != player_request_ids.get(player_name) or player_name != active_player:
                    logging.info(f"Request {req_id} for '{player_name}' is obsolete. Skipping movie genre lookup.")
                    return
                genre = query_llm_for_movie_genre(cleaned_title)
                
                # Verify if this is still the active request
                if req_id != player_request_ids.get(player_name) or player_name != active_player:
                    logging.info(f"Request {req_id} for '{player_name}' is obsolete. Discarding LLM result '{genre}'.")
                    return
                    
                if genre and genre in MOVIE_GENRE_TO_PRESET:
                    preset = MOVIE_GENRE_TO_PRESET[genre]
                    logging.info(f"Mapped movie genre '{genre}' to preset: {preset}")
                else:
                    logging.info(f"Could not determine movie preset. Falling back to default: {DEFAULT_MOVIE_PRESET}")
                    preset = DEFAULT_MOVIE_PRESET
                
        else:
            logging.info(f"Unrecognized browser media type. Falling back to default: {DEFAULT_PRESET}")
            preset = DEFAULT_PRESET
            
    elif is_video_player(player_name):
        media_type = "movie"
        logging.info(f"Processing video player '{player_name}': {title} (Req: {req_id})")
        
        # Clean title
        cleaned_title = clean_video_title(title)
        logging.info(f"Cleaned video title: '{cleaned_title}'")
        
        # 1. Check override mapping (using cleaned title and raw title)
        preset = get_mapping_override(None, None, cleaned_title)
        if not preset:
            preset = get_mapping_override(None, None, title)
            
        if not preset:
            # 2. Query LLM to get genre
            if req_id != player_request_ids.get(player_name) or player_name != active_player:
                logging.info(f"Request {req_id} for '{player_name}' is obsolete. Skipping movie genre lookup.")
                return
            genre = query_llm_for_movie_genre(cleaned_title)
            
            # Verify if this is still the active request
            if req_id != player_request_ids.get(player_name) or player_name != active_player:
                logging.info(f"Request {req_id} for '{player_name}' is obsolete. Discarding LLM result '{genre}'.")
                return
                
            if genre and genre in MOVIE_GENRE_TO_PRESET:
                preset = MOVIE_GENRE_TO_PRESET[genre]
                logging.info(f"Mapped movie genre '{genre}' to preset: {preset}")
            else:
                logging.info(f"Could not determine movie preset. Falling back to default: {DEFAULT_MOVIE_PRESET}")
                preset = DEFAULT_MOVIE_PRESET
            
    else:
        media_type = "music"
        logging.info(f"Processing music player '{player_name}': {title} by {artist} (Req: {req_id})")
        
        # 1. Check override mapping
        preset = get_mapping_override(artist, album, title)
        if not preset:
            # 2. Lookup/Fetch genre-based preset (MusicBrainz + LLM fallback)
            if req_id != player_request_ids.get(player_name) or player_name != active_player:
                logging.info(f"Request {req_id} for '{player_name}' is obsolete. Skipping music genre lookup.")
                return
            preset = get_music_genre_preset(artist)
            
            # Verify if this is still the active request
            if req_id != player_request_ids.get(player_name) or player_name != active_player:
                logging.info(f"Request {req_id} for '{player_name}' is obsolete. Discarding preset '{preset}'.")
                return
                
            if not preset:
                logging.info(f"No specific preset matched. Falling back to default: {DEFAULT_PRESET}")
                preset = DEFAULT_PRESET

    # Verify if this is still the active request before applying and saving status
    if req_id != player_request_ids.get(player_name) or player_name != active_player:
        logging.info(f"Request {req_id} for '{player_name}' is obsolete. Discarding final status save/apply.")
        return

    if preset:
        apply_easyeffects_preset(preset)
        save_status(player_name, metadata, preset, "Playing", media_type)

def process_player_change(player_name, metadata):
    global player_request_ids
    # Generate unique request ID
    req_id = player_request_ids.get(player_name, 0) + 1
    player_request_ids[player_name] = req_id
    
    # Spawn background thread to perform queries non-blockingly
    thread = threading.Thread(
        target=process_player_change_async,
        args=(player_name, metadata, req_id)
    )
    thread.daemon = True
    thread.start()

def get_player_name(bus, unique_name):
    if unique_name in sender_cache:
        return sender_cache[unique_name]
    
    try:
        dbus_obj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
        dbus_iface = dbus.Interface(dbus_obj, 'org.freedesktop.DBus')
        names = dbus_iface.ListNames()
        for name in names:
            if name.startswith("org.mpris.MediaPlayer2."):
                owner = dbus_iface.GetNameOwner(name)
                if owner == unique_name:
                    player_name = name.split("org.mpris.MediaPlayer2.")[1]
                    sender_cache[unique_name] = player_name
                    return player_name
    except Exception as e:
        logging.error(f"Error resolving sender '{unique_name}': {e}")
    return None

def handle_properties_changed(interface_name, changed_properties, invalidated_properties, sender=None):
    global active_player
    if interface_name == "org.mpris.MediaPlayer2.Player" and sender:
        bus = dbus.SessionBus()
        player_name = get_player_name(bus, sender)
        if not player_name:
            return

        if player_name not in players_state:
            players_state[player_name] = {"playback_status": "Stopped", "metadata": {}}

        status_changed = False
        metadata_changed = False

        if "PlaybackStatus" in changed_properties:
            status = str(changed_properties["PlaybackStatus"])
            players_state[player_name]["playback_status"] = status
            status_changed = True
            logging.info(f"Player '{player_name}' playback status changed to: {status}")

        if "Metadata" in changed_properties:
            metadata = changed_properties["Metadata"]
            players_state[player_name]["metadata"] = metadata
            metadata_changed = True

        # Determine the active player
        new_active = active_player
        if players_state[player_name]["playback_status"] == "Playing":
            new_active = player_name
        else:
            playing_players = [p for p, s in players_state.items() if s["playback_status"] == "Playing"]
            if playing_players:
                if "spotify" in playing_players:
                    new_active = "spotify"
                else:
                    new_active = playing_players[0]
            else:
                if not active_player:
                    new_active = player_name

        if new_active != active_player or (new_active == player_name and (metadata_changed or status_changed)):
            active_player = new_active
            if players_state[active_player]["metadata"] and players_state[active_player]["playback_status"] == "Playing":
                media_id = get_media_identifier(active_player, players_state[active_player]["metadata"])
                global last_active_media
                if last_active_media != media_id:
                    last_active_media = media_id
                    process_player_change(active_player, players_state[active_player]["metadata"])
                else:
                    # Same media resumed playing, update status file without re-processing preset
                    save_status(active_player, players_state[active_player]["metadata"], last_applied_preset, "Playing")
            else:
                save_status(active_player, players_state[active_player]["metadata"], last_applied_preset, players_state[active_player]["playback_status"])


def handle_name_owner_changed(name, old_owner, new_owner):
    if name.startswith("org.mpris.MediaPlayer2."):
        player_name = name.split("org.mpris.MediaPlayer2.")[1]
        if not new_owner:  # Player exited
            logging.info(f"Player '{player_name}' (owner: {old_owner}) exited.")
            if old_owner in sender_cache:
                del sender_cache[old_owner]
            if player_name in players_state:
                del players_state[player_name]
                global active_player
                if active_player == player_name:
                    active_player = None
                    playing_players = [p for p, s in players_state.items() if s["playback_status"] == "Playing"]
                    if playing_players:
                        active_player = playing_players[0]
                        media_id = get_media_identifier(active_player, players_state[active_player]["metadata"])
                        global last_active_media
                        last_active_media = media_id
                        process_player_change(active_player, players_state[active_player]["metadata"])
                    elif players_state:
                        active_player = list(players_state.keys())[0]
                        save_status(active_player, players_state[active_player]["metadata"], last_applied_preset, players_state[active_player]["playback_status"])
                    else:
                        save_status(None, None, last_applied_preset, "Stopped")
        else:
            logging.info(f"Player '{player_name}' (owner: {new_owner}) registered.")
            sender_cache[new_owner] = player_name
            if player_name not in players_state:
                players_state[player_name] = {"playback_status": "Stopped", "metadata": {}}

def init_active_players(bus):
    global active_player
    try:
        dbus_obj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
        dbus_iface = dbus.Interface(dbus_obj, 'org.freedesktop.DBus')
        names = dbus_iface.ListNames()
        for name in names:
            if name.startswith("org.mpris.MediaPlayer2."):
                player_name = name.split("org.mpris.MediaPlayer2.")[1]
                owner = dbus_iface.GetNameOwner(name)
                sender_cache[owner] = player_name
                
                try:
                    player_obj = bus.get_object(name, "/org/mpris/MediaPlayer2")
                    properties = dbus.Interface(player_obj, "org.freedesktop.DBus.Properties")
                    status = str(properties.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
                    metadata = properties.Get("org.mpris.MediaPlayer2.Player", "Metadata")
                    
                    players_state[player_name] = {
                        "playback_status": status,
                        "metadata": metadata
                    }
                    logging.info(f"Initialized player '{player_name}' (status: {status})")
                except Exception as ex:
                    logging.warning(f"Failed to fetch state for player '{player_name}': {ex}")
        
        playing_players = [p for p, s in players_state.items() if s["playback_status"] == "Playing"]
        if playing_players:
            if "spotify" in playing_players:
                active_player = "spotify"
            else:
                active_player = playing_players[0]
        elif players_state:
            active_player = list(players_state.keys())[0]
            
        if active_player and players_state[active_player]["metadata"]:
            media_id = get_media_identifier(active_player, players_state[active_player]["metadata"])
            global last_active_media
            last_active_media = media_id
            process_player_change(active_player, players_state[active_player]["metadata"])
        else:
            save_status(active_player, players_state.get(active_player, {}).get("metadata") if active_player else None, None, players_state.get(active_player, {}).get("playback_status", "Stopped") if active_player else "Stopped")
            
    except Exception as e:
        logging.error(f"Error initializing active players: {e}")

def main():
    logging.info("Starting EasyEffects Multi-Player Switcher Daemon...")
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    
    # Subscribe to DBus properties changes with sender keyword
    bus.add_signal_receiver(
        handle_properties_changed,
        dbus_interface="org.freedesktop.DBus.Properties",
        signal_name="PropertiesChanged",
        path="/org/mpris/MediaPlayer2",
        sender_keyword="sender"
    )
    
    # Subscribe to NameOwnerChanged to track player registration/lifecycle
    bus.add_signal_receiver(
        handle_name_owner_changed,
        dbus_interface="org.freedesktop.DBus",
        signal_name="NameOwnerChanged"
    )
    
    # Process currently playing media immediately on startup
    init_active_players(bus)

    # Enter main loop
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        logging.info("Stopping Daemon...")

if __name__ == "__main__":
    main()
