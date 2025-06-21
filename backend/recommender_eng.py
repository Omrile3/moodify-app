import pandas as pd
import numpy as np
import random
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler
from utils import (
    convert_tempo_to_bpm,
    bpm_to_tempo_category,
    fuzzy_match_artist_song,
    generate_chat_response,
    extract_preferences_from_message,
    split_mode_category,
    build_recommendation_key,
    precompute_recommendation_map,
    get_mood_vector,
)

DATA_PATH = "data/songs.csv"
try:
    df = pd.read_csv(DATA_PATH)
except Exception as e:
    print("[RECOMMENDER] Failed to load CSV:", e)
    df = pd.DataFrame([])

df["tempo_raw"] = pd.to_numeric(df.get("tempo", 100), errors="coerce")
features = ['valence', 'energy', 'danceability', 'acousticness', 'tempo']
df = df.dropna(subset=features)
df[features] = df[features].apply(pd.to_numeric, errors='coerce')
df = df.dropna(subset=features)
scaler = MinMaxScaler()
df[features] = scaler.fit_transform(df[features])
recommendation_map = precompute_recommendation_map(df)

SAD_MOODS = {"sad", "melancholy", "down", "emotional", "blue", "heartbreak", "gloomy"}
HAPPY_MOODS = {"happy", "joy", "energetic", "upbeat", "party", "celebrate", "excited"}
UPBEAT_WORDS = {"upbeat", "party", "dance", "energetic", "celebrate", "hyped", "intense"}
SLOW_WORDS = {"slow", "ballad", "chill", "calm"}

def normalize(val):
    if isinstance(val, str):
        return val.strip().lower()
    return val

def weighted_score(row, prefs):
    mood = normalize(row.get('mode_category', '')) if 'mode_category' in row else ''
    genre = normalize(row.get('playlist_genre', '')) if 'playlist_genre' in row else ''
    tempo = normalize(row.get('tempo_category', '')) if 'tempo_category' in row else ''
    artist = normalize(row.get('track_artist', '')) if 'track_artist' in row else ''
    track_name = normalize(row.get('track_name', '')) if 'track_name' in row else ''
    if not mood and 'mood' in row:
        mood = normalize(row.get('mood', ''))

    score = 0
    if prefs.get("genre"):
        pgenre = normalize(prefs["genre"])
        if pgenre and pgenre in genre:
            score += 8
    if prefs.get("mood"):
        pmood = normalize(prefs["mood"])
        if pmood and pmood in mood:
            score += 8
        elif pmood in SAD_MOODS and any(x in mood for x in SAD_MOODS):
            score += 8
        elif pmood in SAD_MOODS and any(x in mood for x in HAPPY_MOODS):
            score -= 10
        elif pmood and pmood in mood:
            score += 3
    if prefs.get("tempo"):
        ptempo = normalize(prefs["tempo"])
        if ptempo and ptempo in tempo:
            score += 8
        elif ptempo in SLOW_WORDS and any(x in tempo for x in SLOW_WORDS):
            score += 8
        elif ptempo in SLOW_WORDS and any(x in tempo for x in UPBEAT_WORDS):
            score -= 5
        elif ptempo and ptempo in tempo:
            score += 2
    if prefs.get("artist_or_song"):
        query = normalize(prefs["artist_or_song"])
        if query and (query in artist or query in track_name):
            score += 10  # Stronger boost for direct match
    pop_val = row.get('track_popularity', row.get('popularity', None))
    if pop_val is not None and not pd.isnull(pop_val):
        try:
            score += float(pop_val) / 100.0
        except Exception:
            pass
    if prefs.get("mood") and normalize(prefs["mood"]) in SAD_MOODS:
        if any(w in mood for w in HAPPY_MOODS | UPBEAT_WORDS):
            score -= 7
    if prefs.get("tempo") and normalize(prefs["tempo"]) in SLOW_WORDS:
        if any(w in tempo for w in UPBEAT_WORDS):
            score -= 3
    return score

def recommend_engine(preferences: dict, api_key: str):
    must_have = ["genre", "mood", "tempo", "artist_or_song"]
    for k in must_have:
        if k not in preferences or (preferences[k] is None and not preferences.get(f"no_pref_{k}", False)):
            return None

    def apply_filters(preferences, filter_tempo=True, filter_genre=True, exclude_artist=None):
        local_df = df.copy()
        mood_str = preferences.get("mood")
        mood_vec = None
        if mood_str:
            mood_vec = get_mood_vector(mood_str, api_key)
        if preferences.get("artist_or_song"):
            local_df = fuzzy_match_artist_song(local_df, preferences["artist_or_song"])
        if filter_genre and preferences.get("genre"):
            local_df = local_df[local_df['playlist_genre'].str.lower() == preferences["genre"].lower()]
        if filter_tempo and preferences.get("tempo"):
            bpm_range = convert_tempo_to_bpm(preferences["tempo"])
            local_df = local_df[(local_df['tempo_raw'] >= bpm_range[0]) & (local_df['tempo_raw'] <= bpm_range[1])]
        if mood_vec is not None and not local_df.empty:
            similarities = cosine_similarity(np.array(mood_vec).reshape(1, -1), local_df[features].values).flatten()
            local_df["similarity"] = similarities
            local_df = local_df.sort_values(by="similarity", ascending=False)
        if exclude_artist:
            local_df = local_df[local_df["track_artist"].str.lower() != exclude_artist.lower()]
        return local_df

    def exclude_history(df, history):
        if not history or df.empty:
            return df
        return df[
            ~df.apply(lambda row: (row["track_name"], row["track_artist"]) in history, axis=1)
        ]

    exclude_artist = None
    if preferences.get("artist_or_song"):
        lowered = preferences["artist_or_song"].lower()
        similarity_request_keywords = [
            "similar to", "like", "vibe like", "in the style of",
            "another artist like", "by a similar artist", "reminiscent of", "same vibe as", "any artist"
        ]
        if any(kw in lowered for kw in similarity_request_keywords):
            for artist in df['track_artist'].dropna().unique():
                if artist.lower() in lowered:
                    exclude_artist = artist
                    preferences["artist_or_song"] = artist
                    break

    filtered = apply_filters(preferences, filter_tempo=True, filter_genre=True, exclude_artist=exclude_artist)
    history = preferences.get("history", [])
    filtered = exclude_history(filtered, history)
    if filtered.empty:
        filtered = apply_filters(preferences, filter_tempo=False, filter_genre=True, exclude_artist=exclude_artist)
        filtered = exclude_history(filtered, history)
    if filtered.empty:
        filtered = apply_filters(preferences, filter_tempo=False, filter_genre=False, exclude_artist=exclude_artist)
        filtered = exclude_history(filtered, history)

    top = None

    if not filtered.empty:
        filtered = filtered.copy()
        filtered["weighted_score"] = filtered.apply(lambda row: weighted_score(row, preferences), axis=1)
        filtered = filtered.sort_values(by="weighted_score", ascending=False)
        for _, row in filtered.iterrows():
            if (row["track_name"], row["track_artist"]) not in history:
                top = row
                history.append((row["track_name"], row["track_artist"]))
                break
        if top is None and not filtered.empty:
            top = filtered.iloc[0]
            history.append((top["track_name"], top["track_artist"]))
    else:
        # Fallback: recommend the most popular song globally (never fails)
        if not df.empty:
            fallback = df.sort_values(by="popularity" if "popularity" in df.columns else "track_popularity", ascending=False)
            for _, row in fallback.iterrows():
                if (row["track_name"], row["track_artist"]) not in history:
                    top = row
                    history.append((row["track_name"], row["track_artist"]))
                    break
            if top is None and not fallback.empty:
                top = fallback.iloc[0]
                history.append((top["track_name"], top["track_artist"]))
        else:
            return {
                "song": "N/A",
                "artist": "N/A",
                "genre": "N/A",
                "mood": preferences.get("mood", "Unknown"),
                "tempo": "Unknown",
                "spotify_url": None
            }

    preferences["history"] = history

    tempo_category = bpm_to_tempo_category(top.get("tempo_raw", 100))
    track_id = top.get("track_id")
    spotify_url = None
    if (
        track_id 
        and isinstance(track_id, str)
        and track_id.lower() != "none"
        and track_id.strip() != ""
        and len(track_id.strip()) == 22
        and track_id.strip().isalnum()
    ):
        spotify_url = f"https://open.spotify.com/track/{track_id.strip()}"

    response = {
        "song": top.get("track_name", "Unknown"),
        "artist": top.get("track_artist", "Unknown"),
        "genre": top.get("playlist_genre", "Unknown"),
        "mood": preferences.get("mood", "Unknown"),
        "tempo": tempo_category,
        "spotify_url": spotify_url
    }

    if preferences.get("artist_or_song"):
        requested = preferences["artist_or_song"].lower()
        if top.get("track_artist", "").lower() != requested and requested not in top.get("track_artist", "").lower():
            response["artist_not_found"] = True
            response["requested_artist"] = requested

    return response
