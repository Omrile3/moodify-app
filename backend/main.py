from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from typing import Optional
import logging

from recommender_eng import recommend_engine
from memory import SessionMemory
from utils import generate_chat_response, extract_preferences_from_message, next_ai_message

# Load OpenAI key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

BUTTONS_HTML = """
<br>
<div style='margin-top:10px;display:flex;gap:8px;flex-wrap:wrap'>
  <button onclick="window.handleBotReply('yes')">👍 Yes, I love it!</button>
  <button onclick="window.handleBotReply('no')">🔄 Recommend another</button>
  <button onclick="window.handleBotReply('change mood')">Change mood</button>
  <button onclick="window.handleBotReply('change genre')">Change genre</button>
  <button onclick="window.handleBotReply('change artist')">Change artist</button>
  <button onclick="window.handleBotReply('change tempo')">Change tempo</button>
</div>
"""

app = FastAPI()
memory = SessionMemory()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://moodify-frontend-j7oz.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

class PreferenceInput(BaseModel):
    session_id: str
    genre: Optional[str] = None
    mood: Optional[str] = None
    tempo: Optional[str] = None
    artist_or_song: Optional[str] = None

class CommandInput(BaseModel):
    session_id: str
    command: str

def has_all_preferences(session):
    required = ["genre", "mood", "tempo", "artist_or_song"]
    for key in required:
        if not (session.get(key) is not None or session.get(f"no_pref_{key}", False)):
            return False
    return True

def get_valid_recommendation(session):
    attempts = 0
    max_attempts = 20
    last_songs = set(session.get("history", []))
    while attempts < max_attempts:
        song = recommend_engine(session, api_key=OPENAI_API_KEY)
        if not song or song.get('song') == "N/A":
            attempts += 1
            continue
        spotify_url = song.get("spotify_url")
        # Always accept top song; embed if Spotify link, else return anyway
        return song
    # As absolute fallback, recommend most popular global song (from recommend_engine fallback)
    return recommend_engine({k: None for k in ["genre","mood","tempo","artist_or_song"]}, api_key=OPENAI_API_KEY)

NO_PREF_WORDS = {
    "no", "none", "no preference", "nothing", "any", "whatever", "anything",
    "doesn't matter", "no specific preference", "all good", "whatever works", "up to you"
}

def user_message_is_no_pref(user_msg):
    user_msg_lower = user_msg.strip().lower()
    return any(word in user_msg_lower for word in NO_PREF_WORDS)

@app.post("/recommend")
def recommend(preference: PreferenceInput):
    session = memory.get_session(preference.session_id)
    all_fields = ["genre", "mood", "tempo", "artist_or_song"]

    user_message = (
        preference.artist_or_song
        or preference.genre
        or preference.mood
        or preference.tempo
        or ""
    )

    # Never block recommendations just because of "awaiting_feedback"
    # Instead, if user sends new preference text, treat as feedback + update
    extracted = extract_preferences_from_message(user_message, OPENAI_API_KEY)

    # Update preferences
    for key in all_fields:
        if session.get(key) is None and not session.get(f"no_pref_{key}", False):
            val = extracted.get(key)
            if val:
                memory.update_session(preference.session_id, key, val)
                memory.update_session(preference.session_id, f"no_pref_{key}", False)
            elif user_message_is_no_pref(user_message):
                memory.update_session(preference.session_id, f"no_pref_{key}", True)

    session = memory.get_session(preference.session_id)

    # Only recommend after all preferences are present/skipped
    if has_all_preferences(session):
        song = get_valid_recommendation(session)
        if not song or song.get("song", "").lower() == "n/a":
            return {
                "response": "<span style='color:green'>I couldn’t find a perfect match, but here’s something popular you might like. Want to try a different mood, artist, or genre?</span>"
            }
        memory.update_last_song(preference.session_id, song['song'], song['artist'])
        gpt_message = generate_chat_response(song, session, OPENAI_API_KEY)
        memory.update_session(preference.session_id, "awaiting_feedback", True)
        memory.update_session(preference.session_id, "followup_count", 0)
        return {"response": f"<span style='color:green'>{gpt_message}</span><br>Are you happy with this recommendation?{BUTTONS_HTML}"}

    # Otherwise, ask for the next missing one
    known_prefs = {k: session.get(k) for k in all_fields}
    missing = [k for k in all_fields if not (session.get(k) is not None or session.get(f"no_pref_{k}", False))]
    no_prefs = [k for k in all_fields if session.get(f"no_pref_{k}", False)]

    context = (
        f"Known preferences: {known_prefs}. "
        f"Still missing: {missing}. "
        f"User said no preference for: {no_prefs}."
    )

    ai_message = next_ai_message(session, user_message + "\n\n" + context, OPENAI_API_KEY)
    memory.update_session(preference.session_id, "followup_count", session.get("followup_count", 0) + 1)
    return {"response": f"<span style='color:green'>{ai_message}</span>"}

@app.post("/command")
def handle_command(command_input: CommandInput):
    cmd = command_input.command.lower().strip()
    session_id = command_input.session_id
    session = memory.get_session(session_id)
    all_fields = ["genre", "mood", "tempo", "artist_or_song"]

    # Handle preference changes
    for pref in ["genre", "mood", "tempo", "artist"]:
        if f"change {pref}" in cmd or f"switch {pref}" in cmd or f"new {pref}" in cmd or (pref in cmd and "change" in cmd):
            field = "artist_or_song" if pref == "artist" else pref
            memory.update_session(session_id, field, None)
            memory.update_session(session_id, f"no_pref_{field}", False)
            memory.update_session(session_id, "awaiting_feedback", False)
            return {
                "response": f"<span style='color:green'>Sure! What {pref} would you like instead?</span>"
            }

    # Hard reset
    if any(word in cmd for word in ["start over", "restart", "reset"]):
        memory.reset_session(session_id)
        return {
            "response": (
                "🔁 <span style='color:green'>Alright! Let’s start fresh. How are you feeling right now?</span>"
            )
        }

    # "another" recommendation (recommend again with same prefs, different song)
    if any(word in cmd for word in ["another", "again", "next one"]):
        session = memory.get_session(session_id)
        session["history"] = [(session.get("last_song"), session.get("last_artist"))]
        song = get_valid_recommendation(session)
        if not song or song.get("song", "").lower() == "n/a":
            return {"response": "<span style='color:green'>I couldn’t find another new song. Want to change mood, genre, artist, or tempo?</span>"}
        memory.update_last_song(session_id, song['song'], song['artist'])
        gpt_message = generate_chat_response(song, session, OPENAI_API_KEY)
        memory.update_session(session_id, "awaiting_feedback", True)
        return {"response": f"<span style='color:green'>{gpt_message}</span><br>Are you happy with this recommendation?{BUTTONS_HTML}"}

    # Feedback after recommendation (locked state, but always actionable)
    if session.get("awaiting_feedback"):
        # Negative feedback: no/try again
        if any(word in cmd for word in ["no", "didn't", "not really", "did not", "nah", "not a good fit", "not fit", "try again"]):
            last_song = session.get("last_song")
            last_artist = session.get("last_artist")
            if last_song and last_artist:
                if (last_song, last_artist) not in session["history"]:
                    session["history"].append((last_song, last_artist))
            song = get_valid_recommendation(session)
            if not song or song.get("song", "").lower() == "n/a":
                memory.update_session(session_id, "awaiting_feedback", False)
                return {
                    "response": "<span style='color:green'>I couldn’t find another new song. Want to change mood, genre, artist, or tempo?</span>"
                }
            memory.update_last_song(session_id, song['song'], song['artist'])
            gpt_message = generate_chat_response(song, session, OPENAI_API_KEY)
            memory.update_session(session_id, "awaiting_feedback", True)
            return {"response": f"<span style='color:green'>{gpt_message}</span><br>Are you happy with this recommendation?{BUTTONS_HTML}"}
        # Positive feedback
        if any(word in cmd for word in ["yes", "love", "liked", "good", "great", "perfect", "awesome", "sure"]):
            memory.update_session(session_id, "awaiting_feedback", False)
            return {
                "response": (
                    "😊 <span style='color:green'>Great! Glad you liked it. If you want to hear something else, just type 'reset' to start again any time!</span>"
                )
            }
        # Handle user specifying new preference while in feedback
        extracted = extract_preferences_from_message(cmd, OPENAI_API_KEY)
        extracted_any = any(extracted.get(k) for k in ["genre", "mood", "tempo", "artist_or_song"])
        if extracted_any:
            for key in ["genre", "mood", "tempo", "artist_or_song"]:
                if extracted.get(key):
                    memory.update_session(session_id, key, extracted[key])
            song = get_valid_recommendation(session)
            if not song or song.get("song", "").lower() == "n/a":
                memory.update_session(session_id, "awaiting_feedback", False)
                return {
                    "response": "<span style='color:green'>I couldn’t find another new song. Want to change mood, genre, artist, or tempo?</span>"
                }
            memory.update_last_song(session_id, song['song'], song['artist'])
            gpt_message = generate_chat_response(song, session, OPENAI_API_KEY)
            memory.update_session(session_id, "awaiting_feedback", True)
            return {"response": f"<span style='color:green'>{gpt_message}</span><br>Are you happy with this recommendation?{BUTTONS_HTML}"}
        # Fallback
        return {"response": "<span style='color:green'>You can say 'another one', 'change genre', 'change artist', 'change mood', 'change tempo', or 'reset' to start over.</span>"}

    if "change" in cmd or "something else" in cmd or "different" in cmd:
        return {
            "response": (
                "<span style='color:green'>Which preference would you like to change? (genre, mood, tempo, or artist)</span>"
            )
        }
    return {"response": "<span style='color:green'>You can say 'another one', 'change genre', 'change artist', 'change mood', 'change tempo', or 'reset' to start over.</span>"}

@app.post("/reset")
def reset_session(command_input: CommandInput):
    session_id = command_input.session_id
    memory.reset_session(session_id)
    return {
        "response": (
            "🔄 <span style='color:green'>Preferences reset! Tell me how you’re feeling or what type of music you want to hear.</span>"
        )
    }

@app.get("/session/{session_id}")
def get_session(session_id: str):
    return memory.get_session(session_id)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    error_details = traceback.format_exc()
    print(f"[GLOBAL ERROR] Unhandled exception: {exc}\nDetails:\n{error_details}")
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected error occurred. Please try again later."},
    )

@app.get("/test-cors")
def test_cors():
    return {"message": "CORS is working!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")), reload=True)
