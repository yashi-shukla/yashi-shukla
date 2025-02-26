import os
import json
import requests
import logging
from base64 import b64encode
from flask import Flask, request, jsonify
from dotenv import load_dotenv, find_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(find_dotenv())

# Load environment variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET_ID = os.getenv("SPOTIFY_SECRET_ID")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:5000/callback")

# Validate required environment variables
if not all([SPOTIFY_CLIENT_ID, SPOTIFY_SECRET_ID]):
    logger.error("Missing required Spotify environment variables")
    raise EnvironmentError("Missing required Spotify environment variables")

TOKEN_URL = "https://accounts.spotify.com/api/token"

app = Flask(__name__)

def getAuth():
    return b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET_ID}".encode()).decode("ascii")

@app.route("/callback")
def callback():
    code = request.args.get("code")
    
    if not code:
        return jsonify({"error": "Authorization code not found"}), 400
    
    try:
        # Exchange the authorization code for tokens
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI
        }
        
        headers = {
            "Authorization": f"Basic {getAuth()}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post(TOKEN_URL, data=payload, headers=headers)
        response.raise_for_status()
        
        tokens = response.json()
        
        # Return the refresh token in a user-friendly page
        return f"""
        <html>
            <head>
                <title>Spotify Authorization Complete</title>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        text-align: center;
                        line-height: 1.6;
                    }}
                    .container {{
                        background-color: #f5f5f5;
                        border-radius: 10px;
                        padding: 20px;
                        margin-top: 40px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    }}
                    .token {{
                        background-color: #1DB954;
                        color: white;
                        padding: 10px;
                        border-radius: 5px;
                        word-break: break-all;
                        margin: 20px 0;
                        font-family: monospace;
                        font-size: 14px;
                    }}
                    h1 {{ color: #1DB954; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Authorization Successful!</h1>
                    <p>Your Spotify refresh token is:</p>
                    <div class="token">{tokens.get('refresh_token')}</div>
                    <p>Add this token to your environment variables as SPOTIFY_REFRESH_TOKEN</p>
                    <p>Keep this token secure and do not share it with others.</p>
                </div>
            </body>
        </html>
        """
    except requests.exceptions.RequestException as e:
        logger.error(f"Error exchanging code for tokens: {str(e)}")
        return jsonify({"error": f"Failed to exchange code for tokens: {str(e)}"}), 500
    except KeyError as e:
        logger.error(f"Invalid response format: {json.dumps(response.json())}")
        return jsonify({"error": "Invalid response from Spotify"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000) 