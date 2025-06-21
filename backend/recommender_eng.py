import pandas as pd

SONG_CSV_PATH = "songs.csv"
df = pd.read_csv(SONG_CSV_PATH)
df.columns = [c.strip() for c in df.columns]

def recommend_engine(prefs, history=None):
    candidates = df.copy()
    if prefs.get("genre"):
        candidates = candidates[candidates["playlist_genre"].str.lower() == prefs["genre"].lower()]
    if prefs.get("mood"):
        candidates = candidates[candidates["recommendation_key"].str.lower().str.contains(prefs["mood"].lower())]
    if prefs.get("artist"):
        candidates = candidates[candidates["track_artist"].str.lower() == prefs["artist"].lower()]
    if prefs.get("tempo"):
        candidates = candidates[candidates["tempo_category"].str.lower() == prefs["tempo"].lower()]
    # Avoid repeats from history
    if history:
        candidates = candidates[~candidates["track_id"].isin(history)]
    if candidates.empty:
        return None
    row = candidates.sample(1).iloc[0]
    return row
