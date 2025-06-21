import difflib
import requests
import json
import re
import pandas as pd
import base64
import os

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"  

GENRES = {
    "pop", "rock", "classical", "jazz", "metal", "electronic", "hip hop", "rap",
    "r&b", "lofi", "latin", "folk", "reggae", "country", "blues", "indie"
}

MOODS = {
    "happy", "sad", "energetic", "calm", "nostalgic", "romantic", "angry",
    "hopeful", "mellow", "funky", "anxious", "relaxed", "bittersweet", "uplifting", "melancholy",
    "dreamy", "groovy", "chilled", "moody", "dark", "powerful", "rebellious", "relaxing",
    "intense", "soulful", "epic", "bright", "mysterious", "passionate", "sensual", "tropical",
    "atmospheric", "playful", "fierce", "gritty", "peaceful", "chill", "smooth", "melancholic"
}

NONE_LIKE = {
    "no", "none", "nah", "not really", "nothing", "any", "anything", "whatever",
    "doesn't matter", "does not matter", "no preference", "up to you",
    "anything is fine", "i don't care", "i don't mind", "doesn't matter to me", "no specific preference", "no prefernce"
}

VAGUE_TO_MOOD = {
    "something good": "happy",
    "good": "happy",
    "positive": "happy",
    "uplifting": "happy",
    "something fun": "happy",
    "something sad": "sad",
    "more energy": "energetic",
    "energy": "energetic",
    "energetic": "energetic",
    "calm": "calm",
    "chill": "calm",
}

HARDCODED_MOOD_VECTORS = {
    # ... [no change for brevity, same as before]
}
_MOOD_VECTOR_CACHE = {}

def get_mood_vector(mood, api_key, fallback=HARDCODED_MOOD_VECTORS):
    mood = mood.lower().strip()
    if mood in _MOOD_VECTOR_CACHE:
        return _MOOD_VECTOR_CACHE[mood]
    if mood in fallback:
        return fallback[mood]
    prompt = (
        f"The mood '{mood}' needs to be mapped to a 5-dimensional music feature vector: "
        "valence (happiness), energy, danceability, acousticness, and tempo, each as a number between 0 and 1. "
        "Respond ONLY with a Python list of 5 floats between 0 and 1, e.g. [0.8, 0.7, 0.9, 0.2, 0.6]."
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are an expert at mapping musical moods to audio feature vectors."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 64
    }
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
        arr = None
        match = re.search(r"\[([^\[\]]+)\]", text)
        if match:
            arr = match.group(0)
            arr = [float(x.strip()) for x in arr.strip("[]").split(",")]
        if arr and len(arr) == 5 and all(0 <= x <= 1 for x in arr):
            _MOOD_VECTOR_CACHE[mood] = arr
            return arr
    except Exception as e:
        print("[UTILS] GPT mood vector fetch failed, fallback to hardcoded:", e)
    return fallback.get(mood, fallback["calm"])

def convert_tempo_to_bpm(tempo_category: str) -> tuple:
    return {
        'slow': (0, 89),
        'medium': (90, 120),
        'fast': (121, 300)
    }.get(tempo_category.lower(), (0, 300))

def bpm_to_tempo_category(bpm: float) -> str:
    if bpm < 90:
        return "slow"
    elif bpm <= 120:
        return "medium"
    else:
        return "fast"

def fuzzy_match_word(word, options, cutoff=0.75):
    if not word:
        return None
    matches = difflib.get_close_matches(word.lower(), options, n=1, cutoff=cutoff)
    if matches:
        return matches[0]
    return None

def fuzzy_match_artist_song(df, query: str):
    if not isinstance(query, str):
        print(f"[UTILS] Invalid query type for fuzzy_match_artist_song: {type(query)}")
        return df.head(5)
    query = query.lower().strip()
    if not query:
        return df.head(5)
    # Try strict match first
    match_artist = df[df['track_artist'].str.lower() == query]
    match_song = df[df['track_name'].str.lower() == query]
    if not match_artist.empty or not match_song.empty:
        return pd.concat([match_artist, match_song]).drop_duplicates()
    # Fuzzy search
    df['track_artist'] = df['track_artist'].fillna("").astype(str).str.lower()
    df['track_name'] = df['track_name'].fillna("").astype(str).str.lower()
    artist_matches = difflib.get_close_matches(query, df['track_artist'], n=5, cutoff=0.6)
    song_matches = difflib.get_close_matches(query, df['track_name'], n=5, cutoff=0.6)
    if artist_matches:
        return df[df['track_artist'].str.lower().isin(artist_matches)]
    elif song_matches:
        return df[df['track_name'].str.lower().isin(song_matches)]
    else:
        return df.nlargest(5, 'popularity') if 'popularity' in df.columns else df.head(5)

def generate_chat_response(song_dict: dict, preferences: dict, api_key: str, custom_prompt: str = None) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    genre = preferences.get('genre') or "any"
    mood = preferences.get('mood') or "any"
    tempo = preferences.get('tempo') or "any"
    song = song_dict.get('song', 'Unknown')
    artist = song_dict.get('artist', 'Unknown')
    song_genre = song_dict.get('genre', 'Unknown')
    song_tempo = song_dict.get('tempo', 'Unknown')
    spotify_url = song_dict.get('spotify_url')
    prompt = custom_prompt or f"""
You are Moodify, a friendly and concise music recommendation assistant.
The user wants a song that matches these preferences:
Genre: {genre}, Mood: {mood}, Tempo: {tempo}.
Recommend only the selected song: "{song}" by {artist} ({song_genre}, {song_tempo} tempo).
If there is a Spotify link available, include 'Listen on Spotify' as a hyperlink.
Reply in a warm and friendly tone. Your response must be short and concise — no more than 1.5 sentences.
Don't suggest alternatives or explain why. Mention only this one song.
"""
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful music assistant. Respond in under 1.5 sentences."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 200
    }
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=body)
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]["content"].strip()
        if spotify_url and isinstance(spotify_url, str) and "open.spotify.com/track/" in spotify_url and len(spotify_url) > 35:
            message += f' 🎵 <a href="{spotify_url}" target="_blank">Listen on Spotify</a>'
        return message
    except Exception as e:
        print("[UTILS] OpenAI Chat Error:", e)
        fallback = f"🎵 Here’s a great track: '{song}' by {artist}."
        if spotify_url and isinstance(spotify_url, str) and "open.spotify.com/track/" in spotify_url and len(spotify_url) > 35:
            fallback += f' <a href="{spotify_url}" target="_blank">Listen</a>'
        return fallback

def extract_preferences_from_message(message: str, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    msg = message.strip().lower()

    def contains_none_like(val):
        for none_str in NONE_LIKE:
            if f" {none_str} " in f" {val} ":
                return True
        return False
    none_fields = {field: contains_none_like(msg) for field in ["genre", "mood", "tempo", "artist_or_song"]}

    mapped = {}
    for phrase, mapped_val in VAGUE_TO_MOOD.items():
        if phrase in msg:
            if mapped_val in MOODS:
                mapped["mood"] = mapped_val
            if mapped_val == "energetic":
                mapped["tempo"] = "fast"
            break

    extracted = {}
    if not any(none_fields.values()):
        mood_list_str = ", ".join(f'"{m}"' for m in sorted(MOODS))
        system_prompt = (
            f"You are an AI that extracts ONLY music preferences from user input in English.\n"
            f"For the 'mood' field, only use one of these values (case-insensitive, single word): [{mood_list_str}].\n"
            "If the user's input doesn't clearly match a mood in the list, set 'mood' to null.\n"
            "If the message is not in English, reply ONLY with this: '__NOT_ENGLISH__'.\n"
            "If the message is not about music, reply ONLY with this: '__NOT_MUSIC__'.\n"
            "Respond only in valid JSON with exactly these 4 keys: genre, mood, tempo, artist_or_song. If a value is not clear, set to null.\n"
            "Never infer or guess outside this set for moods."
        )
        user_prompt = f"""Extract the user's music preferences from the following message.
If genre, mood, tempo, or artist/song is not mentioned or not clear, set to null.
Reply only with the JSON object, nothing else.
Input: "{message}".
"""
        body = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 250
        }
        try:
            response = requests.post(OPENAI_API_URL, headers=headers, json=body)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()
            if text == "__NOT_ENGLISH__":
                extracted = {"genre": None, "mood": None, "tempo": None, "artist_or_song": None, "_not_english": True}
                return extracted
            elif text == "__NOT_MUSIC__":
                extracted = {"genre": None, "mood": None, "tempo": None, "artist_or_song": None, "_not_music": True}
                return extracted
            if text.startswith("```"):
                text = text.lstrip("`")
                text = text[text.find("{"):]
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                json_text = match.group(0)
                try:
                    extracted = json.loads(json_text)
                except Exception as e:
                    print("[UTILS] OpenAI Extraction Error (inner):", e, "| Offending text:", repr(json_text))
                    extracted = {"genre": None, "mood": None, "tempo": None, "artist_or_song": None}
            else:
                print("[UTILS] OpenAI Extraction Error: Could not find JSON object in:", repr(text))
                extracted = {"genre": None, "mood": None, "tempo": None, "artist_or_song": None}
        except Exception as e:
            print("[UTILS] OpenAI Extraction Error:", e)
            extracted = {"genre": None, "mood": None, "tempo": None, "artist_or_song": None}
    else:
        extracted = {"genre": None, "mood": None, "tempo": None, "artist_or_song": None}

    for key in ["genre", "mood", "tempo", "artist_or_song"]:
        if none_fields.get(key):
            extracted[key] = None
        if key in mapped and mapped[key]:
            extracted[key] = mapped[key]
        if extracted.get(key) and isinstance(extracted[key], str):
            val = extracted[key].strip().lower()
            if val in NONE_LIKE:
                extracted[key] = None
            if key == "mood":
                corrected = fuzzy_match_word(val, MOODS)
                extracted[key] = corrected if corrected in MOODS else None
            if key == "genre":
                corrected = fuzzy_match_word(val, GENRES)
                extracted[key] = corrected if corrected in GENRES else None
    return {k: extracted.get(k, None) for k in ["genre", "mood", "tempo", "artist_or_song"]} | {k: v for k, v in extracted.items() if k.startswith("_")}

def split_mode_category(mode_category: str) -> tuple:
    if isinstance(mode_category, str):
        parts = re.split(r'[\s_]+', mode_category.strip())
        return (parts[0].lower(), parts[1].lower()) if len(parts) >= 2 else (parts[0].lower(), None)
    return (None, None)

def build_recommendation_key(genre: str, mood: str, energy: str, tempo: str) -> str:
    return f"{genre}_{mood.capitalize()} {energy.capitalize()}_{tempo.capitalize()}"

def precompute_recommendation_map(df: pd.DataFrame) -> dict:
    index_map = {}
    for _, row in df.iterrows():
        genre = row.get("playlist_genre", "unknown")
        tempo = row.get("tempo_category", "medium")
        mood, energy = split_mode_category(row.get("mode_category", "calm calm"))
        key = build_recommendation_key(genre, mood, energy, tempo)
        if key not in index_map:
            index_map[key] = []
        index_map[key].append(row)
    return index_map

def next_ai_message(session: dict, last_user_message: str, api_key: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    all_keys = ["genre", "mood", "tempo", "artist_or_song"]
    known_prefs = {k: session.get(k) for k in all_keys if session.get(k) is not None}
    missing = [k for k in all_keys if not (session.get(k) is not None or session.get(f"no_pref_{k}", False))]
    no_prefs = [k for k in all_keys if session.get(f"no_pref_{k}", False)]

    system_prompt = (
        "You are Moodify, a friendly, conversational AI music assistant. "
        "Your job is to collect music preferences from the user (genre, mood, tempo, artist or song). "
        "For each, you need a value or a clear 'no preference' message from the user - if they have no preference do not update the field. "
        "Do NOT recommend any song until you have ALL FOUR: genre, mood, tempo, artist_or_song (or 'no preference' for each). "
        "Ask for missing info naturally, but ONLY ask about ONE missing element at a time. Never repeat the same question if the user already said 'no preference' or similar for that element. "
        "Once all are provided, you may recommend. After recommendation, always ask for feedback."
        "If the user's message is off-topic or not in English, gently redirect them to music preferences, and ask in English."
    )

    user_prompt = (
        f"Conversation state:\n"
        f"Known preferences: {known_prefs}\n"
        f"No preference for: {no_prefs}\n"
        f"Still missing: {missing}\n"
        f"User said: \"{last_user_message}\"\n\n"
        "Continue the conversation to collect missing information, in a friendly way. "
        "Only ask about ONE element that is still missing (not 'no preference'). "
        "Do not give a recommendation until everything is filled."
    )

    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=body)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("[UTILS] OpenAI next_ai_message error:", e)
        return "What kind of music do you feel like today?"
