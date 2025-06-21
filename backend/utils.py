import re
from rapidfuzz import process, fuzz
import pandas as pd
from recommender_eng import recommend_engine

SONG_CSV_PATH = "songs.csv"
df = pd.read_csv(SONG_CSV_PATH)
df.columns = [c.strip() for c in df.columns]

GENRES = sorted(set(str(x).lower() for x in df["playlist_genre"].dropna().unique()))
TEMPOS = sorted(set(str(x).lower() for x in df["tempo_category"].dropna().unique()))

# Collect all mood words from recommendation_key
MOODS = set()
for v in df["recommendation_key"].dropna():
    for mood in str(v).split():
        MOODS.add(mood.lower())

ARTISTS = set(str(x) for x in df["track_artist"].dropna().unique())

def fuzzy_match(val, choices, threshold=70):
    if not val: return None
    choices_str = [str(c) for c in choices if pd.notnull(c)]
    matches = process.extract(val.lower(), [c.lower() for c in choices_str], scorer=fuzz.token_set_ratio, limit=1)
    if matches and matches[0][1] >= threshold:
        orig = [c for c in choices_str if c.lower() == matches[0][0]]
        return orig[0] if orig else None
    return None

def extract_preferences_from_message(msg, session):
    m = msg.lower()
    # Extract genre, mood, artist, tempo using fuzzy
    genre = fuzzy_match(m, GENRES)
    mood = fuzzy_match(m, MOODS)
    tempo = fuzzy_match(m, TEMPOS)
    artist = None
    for a in ARTISTS:
        if fuzzy_match(m, [a], 85):  # Higher threshold for artist name
            artist = a
            break
    # Update session
    if genre and not session.get("genre"):
        session["genre"] = genre
    if mood and not session.get("mood"):
        session["mood"] = mood
    if artist and not session.get("artist"):
        session["artist"] = artist
    if tempo and not session.get("tempo"):
        session["tempo"] = tempo
    # Handle "no preference"
    if "no preference" in m or "anything" in m or "doesn't matter" in m:
        for field in ["genre", "mood", "artist", "tempo"]:
            if not session.get(field):
                session[field] = None
                session["no_pref"].add(field)
                break

def next_ai_message(session, message):
    # Update prefs from message
    extract_preferences_from_message(message, session)
    # Feedback phase
    if session["awaiting_feedback"]:
        m = message.lower()
        if "yes" in m or "love" in m or "like" in m:
            session["awaiting_feedback"] = False
            return ("Great! If you want another, just ask.", None)
        elif "another" in m:
            session["history"].add(session["last_rec"])
            rec = recommend_engine(session, session["history"])
            if rec is not None:
                session["last_rec"] = rec["track_id"]
                return (
                    f"Here's another: '{rec['track_name']}' by {rec['track_artist']}.", rec
                )
            else:
                return ("Sorry, I couldn't find another with those preferences.", None)
        elif "change" in m:
            if "genre" in m:
                session["genre"] = None
                session["no_pref"].discard("genre")
            elif "mood" in m:
                session["mood"] = None
                session["no_pref"].discard("mood")
            elif "artist" in m:
                session["artist"] = None
                session["no_pref"].discard("artist")
            elif "tempo" in m:
                session["tempo"] = None
                session["no_pref"].discard("tempo")
            else:
                return ("What would you like to change? (genre, mood, artist, tempo)", None)
            session["awaiting_feedback"] = False
            return (f"Sure! What {', '.join([k for k in ['genre','mood','artist','tempo'] if session[k] is None])} are you in the mood for?", None)
        elif "reset" in m or "start over" in m:
            for k in ["genre", "mood", "artist", "tempo"]:
                session[k] = None
            session["no_pref"] = set()
            session["history"] = set()
            session["awaiting_feedback"] = False
            return ("All preferences reset. What genre are you in the mood for?", None)
        else:
            return ("Let me know if you'd like another recommendation or want to change something.", None)
    # Gather all preferences
    missing = [k for k in ["genre", "mood", "artist", "tempo"] if session.get(k) is None and k not in session["no_pref"]]
    if missing:
        field = missing[0]
        prompts = {
            "genre": "What genre are you in the mood for? (e.g., pop, rock, r&b...)",
            "mood": "What mood are you feeling? (e.g., happy, sad, romantic, energetic...)",
            "artist": "Any favorite artist? (or 'no preference')",
            "tempo": "Do you prefer a slow, medium, or fast tempo? (or 'no preference')"
        }
        return (prompts[field], None)
    # All set: recommend!
    rec = recommend_engine(session, session["history"])
    if rec is None:
        return ("Sorry, I couldn't find a match for those preferences. Try different options.", None)
    session["awaiting_feedback"] = True
    session["last_rec"] = rec["track_id"]
    session["history"].add(rec["track_id"])
    return (
        f"How about '{rec['track_name']}' by {rec['track_artist']}'? Are you happy with this recommendation? (yes/no/another/change [field])",
        rec
    )

def get_spotify_embed(rec):
    track_id = rec["track_id"]
    return f'<div style="margin:14px 0;"><iframe src="https://open.spotify.com/embed/track/{track_id}" width="100%" height="80" frameborder="0" allowtransparency="true" allow="encrypted-media"></iframe></div>'
