import threading
from collections import defaultdict

class SessionMemory:
    def __init__(self):
        self.sessions = defaultdict(lambda: {
            "genre": None,
            "mood": None,
            "tempo": None,
            "artist_or_song": None,
            "no_pref_genre": False,
            "no_pref_mood": False,
            "no_pref_tempo": False,
            "no_pref_artist_or_song": False,
            "awaiting_feedback": False,
            "followup_count": 0,
            "history": [],
            "last_song": None,
            "last_artist": None,
        })
        self.lock = threading.Lock()

    def get_session(self, session_id):
        with self.lock:
            return self.sessions[session_id]

    def update_session(self, session_id, key, value):
        with self.lock:
            self.sessions[session_id][key] = value

    def reset_session(self, session_id):
        with self.lock:
            self.sessions[session_id] = {
                "genre": None,
                "mood": None,
                "tempo": None,
                "artist_or_song": None,
                "no_pref_genre": False,
                "no_pref_mood": False,
                "no_pref_tempo": False,
                "no_pref_artist_or_song": False,
                "awaiting_feedback": False,
                "followup_count": 0,
                "history": [],
                "last_song": None,
                "last_artist": None,
            }

    def update_last_song(self, session_id, song, artist):
        with self.lock:
            self.sessions[session_id]["last_song"] = song
            self.sessions[session_id]["last_artist"] = artist
            # Always add to history (never repeat)
            if (song, artist) not in self.sessions[session_id]["history"]:
                self.sessions[session_id]["history"].append((song, artist))
            # Deduplicate just in case
            seen = set()
            unique = []
            for pair in self.sessions[session_id]["history"]:
                if pair not in seen:
                    unique.append(pair)
                    seen.add(pair)
            self.sessions[session_id]["history"] = unique
