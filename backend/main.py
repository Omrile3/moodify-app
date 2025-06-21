import os
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from memory import SessionMemory
from recommender_eng import recommend_engine
from utils import (
    extract_preferences_from_message, 
    next_ai_message, 
    GENRES, 
    TEMPOS, 
    get_spotify_embed,
)

# FastAPI app setup
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or restrict to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PreferenceInput(BaseModel):
    session_id: str
    message: Optional[str] = None

memory = SessionMemory()

@app.post("/command")
async def command(input: PreferenceInput):
    session_id = input.session_id
    message = input.message or ""
    # Step 1: Get or create session
    session = memory.get_or_create(session_id)
    # Step 2: Parse user input for preferences or feedback
    reply, rec = next_ai_message(session, message)
    # Step 3: If a recommendation is being made, add Spotify embed
    if rec:
        reply += get_spotify_embed(rec)
    # Step 4: Update session memory for follow-up logic
    memory.save(session_id, session)
    return {"response": reply}

@app.post("/reset")
async def reset(input: PreferenceInput):
    memory.reset(input.session_id)
    return {"response": "Preferences reset. Let's start over! What genre are you in the mood for?"}
