import os
import json
import random
import requests
import logging
import time
from io import BytesIO
from base64 import b64encode
from functools import wraps
from dotenv import load_dotenv, find_dotenv
from flask import Flask, Response, jsonify, render_template, abort, request, redirect

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# No color extraction support - using predefined themes instead
COLOR_EXTRACTION_AVAILABLE = False
logger.info("Using predefined color themes")

load_dotenv(find_dotenv())

# Spotify scopes:
#   user-read-currently-playing
#   user-read-recently-played
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET_ID = os.getenv("SPOTIFY_SECRET_ID")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:5000/callback")

# Validate required environment variables
if not all([SPOTIFY_CLIENT_ID, SPOTIFY_SECRET_ID, SPOTIFY_REFRESH_TOKEN]):
    logger.error("Missing required Spotify environment variables")
    raise EnvironmentError("Missing required Spotify environment variables")

REFRESH_TOKEN_URL = "https://accounts.spotify.com/api/token"
NOW_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"
RECENTLY_PLAYING_URL = (
    "https://api.spotify.com/v1/me/player/recently-played?limit=10"
)
AUTH_URL = "https://accounts.spotify.com/authorize"

# Placeholder image for when album art is not available
PLACEHOLDER_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAYAAACM/rhtAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAADISURBVFhH7dY9CsJAFATgWXt/kHgEK/EICpZ6A2/jRbxBGlN4AU9g5R28gZbe77sYlmUTLFZhhDzIA0lmJRD2vTWCRZKkCb6pqoeUydIrKuqgiBjkRlEj8BRFRxblx8RxsKoavw59sfH4j41Sy7JMdrvdeeyPCeOga3a73fV9o9F4NS56CrPZTCEG/VEQML3QqLhYLM4VYliVRB6GpKxzUBoz8aHQ0Gw2k/1+f21ut1t5n8kDH4uiqEF/FGTgF/Otp/Of+RzU2qD/FWAAVoFLO+Fd7ogAAAAASUVORK5CYII="

# Predefined color themes
THEMES = {
    "default": {
        "gradient": "linear-gradient(to right, #1DB954, #191414)",
        "background": "191414",
        "text": "FFFFFF",
        "accent": "1DB954"
    },
    "dark": {
        "gradient": "linear-gradient(to right, #1DB954, #191414)",
        "background": "191414",
        "text": "FFFFFF",
        "accent": "1DB954"
    },
    "light": {
        "gradient": "linear-gradient(to right, #1ED760, #FFFFFF)",
        "background": "FFFFFF",
        "text": "191414",
        "accent": "1ED760"
    },
    "colorful": {
        "gradient": "linear-gradient(to right, #B026FF, #FF8A2E, #1DB954, #4062BB)",
        "background": "0E1118",
        "text": "FFFFFF",
        "accent": "1DB954"
    },
    "purple": {
        "gradient": "linear-gradient(to right, #7B4397, #DC2430)",
        "background": "251431",
        "text": "FFFFFF",
        "accent": "DC2430"
    },
    "beach": {
        "gradient": "linear-gradient(to right, #00C9FF, #92FE9D)",
        "background": "002B40",
        "text": "FFFFFF",
        "accent": "92FE9D"
    }
}

# Default theme
DEFAULT_THEME = THEMES["default"]

# In-memory cache for token
token_cache = {
    "access_token": None,
    "expires_at": 0
}

app = Flask(__name__)


def cached_token(func):
    @wraps(func)
    def wrapper():
        if token_cache["access_token"] and token_cache["expires_at"] > time.time():
            return token_cache["access_token"]
        access_token = func()
        token_cache["access_token"] = access_token
        token_cache["expires_at"] = time.time() + 3600  # Cache for 1 hour
        return access_token
    return wrapper


def getAuth():
    return b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET_ID}".encode()).decode(
        "ascii"
    )


@cached_token
def refreshToken():
    data = {
        "grant_type": "refresh_token",
        "refresh_token": SPOTIFY_REFRESH_TOKEN,
    }

    headers = {"Authorization": "Basic {}".format(getAuth())}
    
    try:
        response = requests.post(REFRESH_TOKEN_URL, data=data, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()["access_token"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise
    except KeyError:
        logger.error(f"Invalid response format: {json.dumps(response.json())}")
        raise KeyError(f"Invalid response from Spotify: {str(response.json())}")


def recentlyPlayed():
    try:
        token = refreshToken()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(RECENTLY_PLAYING_URL, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors

        if response.status_code == 204:
            return {}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching recently played: {str(e)}")
        return {}


def nowPlaying():
    try:
        token = refreshToken()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(NOW_PLAYING_URL, headers=headers, timeout=10)
        
        if response.status_code == 204:
            return {}
        
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching now playing: {str(e)}")
        return {}


def barGen(barCount):
    barCSS = ""
    left = 1
    for i in range(1, barCount + 1):
        anim = random.randint(1000, 1350)
        barCSS += (
            ".bar:nth-child({})  {{ left: {}px; animation-duration: {}ms; }}".format(
                i, left, anim
            )
        )
        left += 4
    return barCSS


def getThemeGradient(theme_name=None):
    """Get gradient for the specified theme"""
    if not theme_name or theme_name not in THEMES:
        return DEFAULT_THEME["gradient"]
    return THEMES[theme_name]["gradient"]


def loadImageB64(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return b64encode(response.content).decode("ascii")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error loading image: {str(e)}")
        # Return a placeholder image
        return PLACEHOLDER_IMAGE


def makeSVG(data, theme=None, background_color=None, border_color=None):
    barCount = 84
    contentBar = "".join(["<div class='bar'></div>" for i in range(barCount)])
    barCSS = barGen(barCount)

    # Get theme properties
    theme_data = THEMES.get(theme, DEFAULT_THEME)

    try:
        if data == {} or data.get("item") is None or data.get("item") == "None":
            contentBar = "" #Shows/Hides the EQ bar if no song is currently playing
            currentStatus = "Was playing:"
            recentPlays = recentlyPlayed()
            
            if not recentPlays or "items" not in recentPlays or not recentPlays["items"]:
                return render_template("error.html.j2", error="No recent songs found")
                
            recentPlaysLength = len(recentPlays["items"])
            itemIndex = random.randint(0, recentPlaysLength - 1)
            item = recentPlays["items"][itemIndex]["track"]
        else:
            item = data["item"]
            currentStatus = "Vibing to:"
        
        # Handle images
        if not item["album"]["images"]:
            image = PLACEHOLDER_IMAGE
        else:
            image_url = item["album"]["images"][1]["url"]
            image = loadImageB64(image_url)
            
        # Use theme gradients
        barPalette = theme_data["gradient"]
        songPalette = theme_data["gradient"]
            
        artistName = item["artists"][0]["name"].replace("&", "&amp;")
        songName = item["name"].replace("&", "&amp;")
        songURI = item["external_urls"]["spotify"]
        artistURI = item["artists"][0]["external_urls"]["spotify"]

        # Use theme colors if not provided by parameters
        if not background_color:
            background_color = theme_data["background"]
        if not border_color:
            border_color = background_color

        dataDict = {
            "contentBar": contentBar,
            "barCSS": barCSS,
            "artistName": artistName,
            "songName": songName,
            "songURI": songURI,
            "artistURI": artistURI,
            "image": image,
            "status": currentStatus,
            "background_color": background_color,
            "border_color": border_color,
            "barPalette": barPalette,
            "songPalette": songPalette,
            "theme": theme
        }

        return render_template("spotify.html.j2", **dataDict)
    except Exception as e:
        logger.error(f"Error generating SVG: {str(e)}")
        return render_template("error.html.j2", error="Unable to generate Spotify card")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    try:
        theme = request.args.get("theme")
        background_color = request.args.get("background_color")
        border_color = request.args.get("border_color")
        
        data = nowPlaying()
        svg = makeSVG(data, theme, background_color, border_color)

        resp = Response(svg, mimetype="image/svg+xml")
        resp.headers["Cache-Control"] = "s-maxage=1"

        return resp
    except Exception as e:
        logger.error(f"Error in route handler: {str(e)}")
        return Response("Error generating Spotify card", status=500)


@app.route("/now-playing")
def now_playing_json():
    """Return JSON data for currently playing track"""
    try:
        data = nowPlaying()
        if data == {} or data.get("item") is None:
            recent = recentlyPlayed()
            if not recent or "items" not in recent or not recent["items"]:
                return jsonify({"error": "No recent songs found"}), 404
            
            item_index = random.randint(0, len(recent["items"]) - 1)
            item = recent["items"][item_index]["track"]
            return jsonify({
                "is_playing": False,
                "item": item
            })
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in now_playing_json: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/recent")
def recently_played_json():
    """Return JSON data for recently played tracks"""
    try:
        data = recentlyPlayed()
        if not data or "items" not in data or not data["items"]:
            return jsonify({"error": "No recent songs found"}), 404
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in recently_played_json: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/auth")
def auth():
    """Initiate Spotify authentication flow"""
    scope = "user-read-currently-playing user-read-recently-played"
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": scope
    }
    auth_url = f"{AUTH_URL}?" + "&".join([f"{k}={v}" for k, v in params.items()])
    return redirect(auth_url)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
