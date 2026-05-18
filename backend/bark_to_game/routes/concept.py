"""Token sequence → game concept translation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from bark_to_game.schemas.concept import (
    Concept,
    GameParams,
    StyleCardRef,
    StyleTriplet,
    TranslateRequest,
    TranslateResponse,
)
from bark_to_game.translate.engine import translate

router = APIRouter(prefix="/api/concept", tags=["concept"])


@router.post("/translate")
async def translate_tokens(req: TranslateRequest) -> TranslateResponse:
    try:
        result = await translate(
            tokens=[t.model_dump() for t in req.tokens],
            summary=req.summary.model_dump(),
            audio_hash=req.audio_hash,
            session_id=req.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # SDK/network/parsing failure
        # Preserve the exception type — httpx.ReadTimeout etc. have an empty
        # str() and would otherwise surface as the bare "translation failed:"
        # message we saw in prod after PR #29.
        body = f"{type(exc).__name__}: {exc!s}" if str(exc) else type(exc).__name__
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"translation failed: {body}",
        ) from exc

    triplet = result["style_triplet"]
    return TranslateResponse(
        chosen=Concept(**result["chosen"]),
        chosen_probability=result["chosen_probability"],
        chosen_score=result["chosen_score"],
        candidate_count=len(result["candidates"]),
        style_triplet=StyleTriplet(
            art=StyleCardRef(
                name=triplet["art"]["name"], description=triplet["art"]["description"]
            ),
            mechanic=StyleCardRef(
                name=triplet["mechanic"]["name"],
                description=triplet["mechanic"]["description"],
            ),
            mood=StyleCardRef(
                name=triplet["mood"]["name"], description=triplet["mood"]["description"]
            ),
        ),
        visual_recipe=result["visual_recipe"],
        game_params=GameParams(**result["game_params"]),
        avoided_summaries=result["avoided_summaries"],
    )
