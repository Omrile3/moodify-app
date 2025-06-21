class SessionMemory:
    def __init__(self):
        self.sessions = {}

    def get_or_create(self, session_id):
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "genre": None,
                "mood": None,
                "artist": None,
                "tempo": None,
                "no_pref": set(),
                "history": set(),  # Track recommended songs (track_id)
                "awaiting_feedback": False,
                "last_rec": None
            }
        return self.sessions[session_id]

    def save(self, session_id, data):
        self.sessions[session_id] = data

    def reset(self, session_id):
        if session_id in self.sessions:
            del self.sessions[session_id]
