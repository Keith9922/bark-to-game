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


def _user_friendly_translate_error(exc: BaseException) -> str:
    """Translate engine exception → message the frontend can show verbatim.

    The engine has its own retry loop for transient failures (5xx, ReadTimeout,
    ConnectError, overloaded_error). Anything that bubbles up here has already
    survived 3 attempts, so a friendly "上游响应慢，请稍后重试" beats the raw
    "upstream busy after N attempts (last: ...)" stack chatter.

    We classify by the engine's wrapper message pattern, falling back to the
    raw exception text so unfamiliar failure modes are still debuggable.
    """
    detail = str(exc) or type(exc).__name__
    if "upstream busy" in detail or "ReadTimeout" in detail or "ConnectError" in detail:
        return (
            "上游响应慢，已自动重试仍未成功，请稍后再试一次。 "
            "(Upstream slow after retries — please try again in a few seconds.)"
        )
    if "rate-limited" in detail or "HTTP 429" in detail:
        return (
            "今日 API 额度已用尽，请稍后再试。"
            "(API quota exhausted — try later.)"
        )
    # Unknown failure — keep the developer-readable detail so we can debug
    # without leaving the user with an opaque error.
    body = f"{type(exc).__name__}: {exc!s}" if str(exc) else type(exc).__name__
    return f"translation failed: {body}"


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
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            _user_friendly_translate_error(exc),
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
