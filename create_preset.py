#!/usr/bin/env python3
import sys
import os
import subprocess
import re
import dbus
import urllib.parse

AGY_PATH = "/home/wh0/.local/bin/agy"



def get_active_player_metadata():
    try:
        bus = dbus.SessionBus()
        dbus_obj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
        dbus_iface = dbus.Interface(dbus_obj, 'org.freedesktop.DBus')
        names = dbus_iface.ListNames()
        
        players = []
        for name in names:
            if name.startswith("org.mpris.MediaPlayer2."):
                player_name = name.split("org.mpris.MediaPlayer2.")[1]
                try:
                    player_obj = bus.get_object(name, "/org/mpris/MediaPlayer2")
                    properties = dbus.Interface(player_obj, "org.freedesktop.DBus.Properties")
                    status = str(properties.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
                    metadata = properties.Get("org.mpris.MediaPlayer2.Player", "Metadata")
                    players.append({
                        "name": player_name,
                        "status": status,
                        "metadata": metadata
                    })
                except Exception:
                    continue
        
        if not players:
            return None
            
        # Prioritize players that are currently playing
        playing = [p for p in players if p["status"] == "Playing"]
        if playing:
            # If multiple are playing, prioritize Spotify (music)
            spotify_playing = [p for p in playing if p["name"] == "spotify"]
            if spotify_playing:
                return spotify_playing[0]
            return playing[0]
            
        return players[0]
    except Exception as e:
        print(f"Error scanning players: {e}")
        return None

def clean_video_title(raw_title):
    title = raw_title
    if "/" in title:
        title = title.split("/")[-1]
    
    title = urllib.parse.unquote(title)
    title = re.sub(r"\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v)$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[\._\-]", " ", title)
    
    tags = [
        r"\b\d{3,4}p\b",
        r"\b[hH]\.?26[45]\b",
        r"\b[hH]e[vV]c\b",
        r"\b[bB]lu[rR]ay\b",
        r"\b[bB][dD][rR]ip\b",
        r"\b[wW][eE][bB]\-?[dD][lL]\b",
        r"\b[hH][dD][tT][vV]\b",
        r"\b[dD][dD][pP]\d\.\d\b",
        r"\b[aA][aA][cC]\b",
        r"\b[dD][tT][sS]\b",
        r"\b[aA][cC]3\b",
        r"\b[yY][tT][sS]\b",
        r"\b[yY]i[fF][yY]\b",
        r"\b[xX]vi[dD]\b",
    ]
    for tag in tags:
        title = re.sub(tag, "", title, flags=re.IGNORECASE)
        
    title = re.sub(r"\s+", " ", title).strip()
    return title

def clean_prefix(name):
    # Keep only alphanumeric and dashes
    return re.sub(r"[^a-zA-Z0-9\-]", "", name.lower().replace(" ", "-"))

def main():
    active = get_active_player_metadata()
    if not active or not active.get("metadata"):
        print("Error: Could not retrieve active media player metadata. Is a player running?")
        sys.exit(1)
        
    player_name = active["name"]
    metadata = active["metadata"]
    
    title = str(metadata.get("xesam:title", ""))
    album = str(metadata.get("xesam:album", ""))
    artists_dbus = metadata.get("xesam:artist", [])
    artists = [str(a) for a in artists_dbus]
    artist = ", ".join(artists) if artists else ""
    
    is_video = (player_name != "spotify")
    
    print(f"Detected media from player '{player_name}':")
    if is_video:
        cleaned_title = clean_video_title(title)
        print(f"  Raw Title:     {title}")
        print(f"  Cleaned Title: {cleaned_title}")
        
        preset_prefix = f"movie-{clean_prefix(cleaned_title)}"
        
        prompt = f"""Please analyze the currently playing movie/video and create a new custom EasyEffects preset for it:
- Raw Title: "{title}"
- Cleaned Title: "{cleaned_title}"
- Source Player: "{player_name}"

Instructions:
1. Research the movie's genre, key sound characteristics (e.g. dynamic range, dialogue level, special effects/bass intensity, musical score type), and general production.
2. List the files in `/home/wh0/.var/app/com.github.wwmm.easyeffects/data/easyeffects/output/` starting with `{preset_prefix}` to see if there are any existing presets (e.g., versioned names like `{preset_prefix}.v1`, `{preset_prefix}.v2`).
3. Design a new, custom EasyEffects output preset JSON tailored for this movie. Use the filename prefix `{preset_prefix}` with a version number suffix, incrementing from any existing versions (e.g., `{preset_prefix}.v1` if it's the first version, or `{preset_prefix}.v2` if `{preset_prefix}.v1` already exists).
4. Save the custom preset to:
   `/home/wh0/.var/app/com.github.wwmm.easyeffects/data/easyeffects/output/<preset_name>.json`
5. Map this movie's cleaned title: "{cleaned_title.lower()}" (and also raw title: "{title.lower()}") under "titles" to the new preset name in `/home/wh0/Programming/easyeffects-switcher/mappings.json` so the switcher daemon will automatically load it next time.
6. Apply the preset immediately in EasyEffects:
   `flatpak run com.github.wwmm.easyeffects -l <preset_name_without_json>`
7. Print a concise summary of your analysis, the design choices you made for the preset (EQ/compression/convolver), the name of the file created, and confirm it was successfully applied.
"""
    else:
        print(f"  Title:  {title}")
        print(f"  Artist: {artist}")
        print(f"  Album:  {album}")
        
        artist_cleaned = clean_prefix(artist)
        title_cleaned = clean_prefix(title)
        preset_prefix = f"{artist_cleaned}-{title_cleaned}"
        
        prompt = f"""Please analyze the currently playing Spotify song and create a new custom EasyEffects preset for it:
- Title: "{title}"
- Artist: "{artist}"
- Album: "{album}"

Instructions:
1. Research the song's genre, key instruments (e.g. acoustic/electric, vocals, bass, steel guitar, synths), and production style.
2. List the files in `/home/wh0/.var/app/com.github.wwmm.easyeffects/data/easyeffects/output/` starting with `{preset_prefix}` to see if there are any existing presets (e.g., versioned names like `{preset_prefix}.v1`, `{preset_prefix}.v2`).
3. Design a new, custom EasyEffects output preset JSON tailored for this track. Use the filename prefix `{preset_prefix}` with a version number suffix, incrementing from any existing versions (e.g., `{preset_prefix}.v1` if it's the first version, or `{preset_prefix}.v2` if `{preset_prefix}.v1` already exists).
4. Save the custom preset to:
   `/home/wh0/.var/app/com.github.wwmm.easyeffects/data/easyeffects/output/<preset_name>.json`
5. Map this song's title: "{title.lower()}" under "titles" to the new preset name in `/home/wh0/Programming/easyeffects-switcher/mappings.json` so the switcher daemon will automatically load it next time.
6. Apply the preset immediately in EasyEffects:
   `flatpak run com.github.wwmm.easyeffects -l <preset_name_without_json>`
7. Print a concise summary of your analysis, the design choices you made for the preset (EQ/compression/convolver), the name of the file created, and confirm it was successfully applied.
"""

    print("\nSpawning Antigravity Agent to analyze media and generate custom preset...")
    
    try:
        cmd = [AGY_PATH, "--print", prompt]
        # Inherit stdin/stdout/stderr so the user can see progress and approve permissions if prompted
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        print(f"\nError: Antigravity agent process failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
