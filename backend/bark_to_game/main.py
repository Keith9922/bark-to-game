"""FastAPI application entrypoint."""

from fastapi import FastAPI
from pydantic import BaseModel

from bark_to_game import __version__

app = FastAPI(
    title="bark-to-game",
    description="Audio analysis and game generation backend",
    version=__version__,
)


class Health(BaseModel):
    status: str
    version: str


@app.get("/health")
async def health() -> Health:
    return Health(status="ok", version=__version__)
