import threading
from collections import defaultdict

class SessionMemory:
    HISTORY_LIMIT = 100

    def __init__(self):
        self.sessions = defaultdict(self._empty_session)
        self.lock = threading.Lock()

    def _empty_session(self):
        return {
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

    def get_session(self, session_id):
        with self.lock:
            return dict(self.sessions[session_id])  # Return a copy for safety

    def update_session(self, session_id, key, value):
        with self.lock:
            self.sessions[session_id][key] = value

    def reset_session(self, session_id):
        with self.lock:
            self.sessions[session_id] = self._empty_session()

    def update_last_song(self, session_id, song, artist):
        with self.lock:
            s = self.sessions[session_id]
            s["last_song"] = song
            s["last_artist"] = artist
            # Always add to history (never repeat)
            pair = (song, artist)
            if pair not in s["history"]:
                s["history"].append(pair)
            # Deduplicate
            seen = set()
            unique = []
            for p in reversed(s["history"]):
                if p not in seen:
                    unique.append(p)
                    seen.add(p)
            s["history"] = list(reversed(unique))
            # Limit history size
            if len(s["history"]) > self.HISTORY_LIMIT:
                s["history"] = s["history"][-self.HISTORY_LIMIT:]
