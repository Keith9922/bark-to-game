"""FastAPI application entrypoint."""

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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
