"""FastAPI application entrypoint."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bark_to_game import __version__
from bark_to_game.routes import audio, concept, game, history, session

app = FastAPI(
    title="bark-to-game",
    description="Audio analysis and game generation backend",
    version=__version__,
)

# Allow the dev frontend (vite on 5173) plus any production origins listed
# in BARK_ALLOWED_ORIGINS (comma-separated). When the bundle is served from
# the same origin as /api/* (nginx + same host), CORS isn't needed at all,
# but a permissive list keeps cross-origin tooling working.
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra = [o.strip() for o in os.getenv("BARK_ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra,
    allow_credentials=True,
    # DELETE is needed for /api/game/job/{id} cancellation; without it the
    # browser's CORS preflight returns 400 and the cancel button silently fails.
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(audio.router)
app.include_router(concept.router)
app.include_router(game.router)
app.include_router(session.router)
app.include_router(history.router)


class Health(BaseModel):
    status: str
    version: str


@app.get("/health")
async def health() -> Health:
    return Health(status="ok", version=__version__)
