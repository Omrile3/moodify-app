import os
import pandas as pd
import re
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import openai
from rapidfuzz import process, fuzz

# Load CSV at startup
SONG_CSV_PATH = "songs.csv"
df = pd.read_csv(SONG_CSV_PATH)
df.columns = [c.strip() for c in df.columns]

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# Allow frontend from anywhere (or restrict to your frontend domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: str
    message: str

# In-memory sessions (clear on restart)
sessions = {}

GENRES = set(df["playlist_genre"].dropna().str.lower())
MOODWORDS = ["sad", "happy", "energetic", "calm", "neutral"]
TEMPOS = set(df["tempo_category"].dropna().str.lower())
ARTISTS = set(df["track_artist"].dropna())

def is_english(s):
    try:
        s.encode('utf-8').decode('ascii')
        return True
    except UnicodeDecodeError:
        return False

def fuzzy_match(val, choices, threshold=75):
    """Return best fuzzy match from choices (as strings, skipping nulls), or None if below threshold."""
    if not val:
        return None
    # Only use non-null, string-cast values for matching
    choices_str = [str(c) for c in choices if pd.notnull(c)]
    matches = process.extract(val.lower(), [c.lower() for c in choices_str], scorer=fuzz.token_set_ratio, limit=1)
    if matches and matches[0][1] >= threshold:
        # Return the original case value from choices_str (not lower)
        orig = [c for c in choices_str if c.lower() == matches[0][0]]
        return orig[0] if orig else None
    return None

def classify_input(message):
    m = message.lower()
    genre = fuzzy_match(m, GENRES)
    tempo = fuzzy_match(m, TEMPOS)
    mood = fuzzy_match(m, MOODWORDS)
    artist = fuzzy_match(m, ARTISTS)
    return genre, mood, artist, tempo

def get_next_missing_prefs(prefs):
    if not prefs["genre"]:
        return "What genre are you in the mood for? (e.g., pop, rock, r&b...)"
    if not prefs["mood"]:
        return "What mood are you in the mood for? (e.g., happy, sad, energetic, calm...)"
    if not prefs["artist"]:
        return "Any favorite artist? (or 'no preference')"
    if not prefs["tempo"]:
        return "Do you prefer a slow, medium, or fast tempo? (or 'no preference')"
    return None

def recommend_song(prefs):
    candidates = df.copy()
    if prefs["genre"]:
        genre_val = fuzzy_match(prefs["genre"], df["playlist_genre"].unique())
        if genre_val:
            candidates = candidates[candidates["playlist_genre"].str.lower() == genre_val.lower()]
    if prefs["mood"]:
        candidates = candidates[
            candidates["recommendation_key"].apply(
                lambda x: bool(fuzzy_match(prefs["mood"], [str(x)]))
            )
        ]
    if prefs["artist"]:
        artist_val = fuzzy_match(prefs["artist"], df["track_artist"].unique())
        if artist_val:
            candidates = candidates[candidates["track_artist"].str.lower() == artist_val.lower()]
    if prefs["tempo"]:
        tempo_val = fuzzy_match(prefs["tempo"], df["tempo_category"].unique())
        if tempo_val:
            candidates = candidates[candidates["tempo_category"].str.lower() == tempo_val.lower()]
    if candidates.empty:
        return None
    row = candidates.sample(1).iloc[0]
    return f"How about '{row['track_name']}' by {row['track_artist']}? 🎶"

def is_music_related(message):
    keywords = ["song", "music", "genre", "artist", "band", "mood", "tempo", "recommend", "track", "playlist"]
    return any(k in message.lower() for k in keywords)

@app.post("/command")
async def command(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    message = body.get("message", "").strip()

    # Init session
    if session_id not in sessions:
        sessions[session_id] = {
            "genre": None, "mood": None, "artist": None, "tempo": None,
            "no_pref": set(),
            "state": "collect"
        }
    prefs = sessions[session_id]

    # English only
    if not is_english(message):
        return {"response": "Sorry, I can only respond to requests in English. Please rephrase your question."}

    # Music only
    if not is_music_related(message) and all(v for v in [prefs["genre"], prefs["mood"], prefs["artist"], prefs["tempo"]]):
        return {"response": "Let's keep our chat about music! Tell me what kind of song, artist, genre, or mood you're looking for."}

    # Classify input (now using fuzzy matching)
    genre, mood, artist, tempo = classify_input(message)
    if genre and not prefs["genre"]:
        prefs["genre"] = genre
    if mood and not prefs["mood"]:
        prefs["mood"] = mood
    if artist and not prefs["artist"]:
        prefs["artist"] = artist
    if tempo and not prefs["tempo"]:
        prefs["tempo"] = tempo

    # No preference handler
    if "no preference" in message.lower() or "anything" in message.lower():
        if not prefs["genre"]:
            prefs["genre"] = None
            prefs["no_pref"].add("genre")
        elif not prefs["mood"]:
            prefs["mood"] = None
            prefs["no_pref"].add("mood")
        elif not prefs["artist"]:
            prefs["artist"] = None
            prefs["no_pref"].add("artist")
        elif not prefs["tempo"]:
            prefs["tempo"] = None
            prefs["no_pref"].add("tempo")

    # If all collected or all marked no pref, recommend
    if all([(prefs["genre"] is not None or "genre" in prefs["no_pref"]),
            (prefs["mood"] is not None or "mood" in prefs["no_pref"]),
            (prefs["artist"] is not None or "artist" in prefs["no_pref"]),
            (prefs["tempo"] is not None or "tempo" in prefs["no_pref"])]):
        suggestion = recommend_song(prefs)
        # Reset for new rec (regardless of found/not found)
        sessions[session_id] = {
            "genre": None, "mood": None, "artist": None, "tempo": None,
            "no_pref": set(),
            "state": "collect"
        }
        if suggestion:
            return {"response": suggestion + " Want another? Just tell me your preferences!"}
        else:
            return {"response": "Sorry, I couldn't find a match for those preferences. Try a different combination?"}

    # Otherwise, ask next
    next_q = get_next_missing_prefs(prefs)
    return {"response": next_q or "Tell me a bit more about what you'd like!"}
