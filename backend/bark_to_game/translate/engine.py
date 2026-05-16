"""Translation orchestrator — Verbalized Sampling + diversity-weighted pick.

Calls Claude via the configured Anthropic Messages API proxy (aipaibox by
default). This is a separate path from the legacy SDK so it doesn't compete
with the user's interactive Claude Code window for Max-plan quota — same
reason the game generator switched in PR #10.

Translate output is small (~700 tokens of JSON) so we use a single
non-streaming POST instead of the streaming flow `_api_backend.py` uses
for the long game generation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any, TypedDict, cast

import httpx
from loguru import logger

from bark_to_game import settings
from bark_to_game.generate._common import RateLimitedError
from bark_to_game.translate import archive, prompts, recipes, style_cards

# Translate is non-streaming and short — give it a tighter ceiling than the
# generate path. If the API takes >60s for a JSON of 5 concepts something is
# very wrong upstream.
_REQUEST_TIMEOUT_S = 60.0


class Concept(TypedDict):
    title: str
    tagline: str
    player: str
    core_mechanic: str
    win_condition: str
    fail_condition: str
    visual_summary: str
    audio_summary: str


class Candidate(TypedDict):
    probability: float
    concept: Concept


class TranslationResult(TypedDict):
    chosen: Concept
    chosen_probability: float
    chosen_score: float
    candidates: list[Candidate]
    style_triplet: style_cards.StyleTriplet
    visual_recipe: str  # recipe name
    avoided_summaries: list[str]


def _seed_from_hash(audio_hash: str) -> int:
    """Stable int seed from the audio SHA prefix."""
    return int(audio_hash[:8], 16)


def _strip_json_fences(text: str) -> str:
    """Tolerate accidental ```json fences around the output."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _max_similarity(text: str, others: list[str]) -> float:
    if not others:
        return 0.0
    return max(SequenceMatcher(None, text.lower(), o.lower()).ratio() for o in others)


def _select(candidates: list[Candidate], recent: list[str]) -> tuple[Candidate, float]:
    """Pick the candidate with the highest `probability * (1 - similarity)`.

    Falls back to highest probability if all summaries are empty.
    """
    best: tuple[Candidate, float] | None = None
    for cand in candidates:
        c = cand["concept"]
        text = f"{c['title']} {c['tagline']} {c['core_mechanic']}"
        sim = _max_similarity(text, recent)
        score = float(cand["probability"]) * (1.0 - sim)
        if best is None or score > best[1]:
            best = (cand, score)
    assert best is not None
    return best


async def _call_claude(system_prompt: str, user_prompt: str) -> str:
    """Non-streaming Messages API call. Returns the concatenated assistant text.

    Raises:
        RuntimeError: missing key, HTTP non-2xx, or unexpected response shape.
        RateLimitedError: HTTP 429 from the proxy.
    """
    if not settings.API_KEY:
        raise RuntimeError(
            "BARK_API_KEY is not set. Set it in backend/.env before calling translate."
        )

    payload = {
        "model": settings.API_TRANSLATE_MODEL,
        "max_tokens": settings.API_TRANSLATE_MAX_OUTPUT_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": settings.API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
        resp = await client.post(
            f"{settings.API_BASE_URL}/v1/messages", headers=headers, json=payload
        )
        if resp.status_code == 429:
            raise RateLimitedError(
                f"translate API rate-limited (HTTP 429): {resp.text[:300]}",
                resets_at=None,
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"translate API HTTP {resp.status_code}: {resp.text[:300]}"
            )
        body = resp.json()

    content = body.get("content") or []
    text_parts = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if not text_parts:
        # Explicit failure beats a downstream JSONDecodeError on "" — the
        # proxy returned 200 with no text content (often: only tool_use
        # blocks, or empty content array from a content-filter trip).
        raise RuntimeError(
            f"translate API returned no text content: "
            f"stop_reason={body.get('stop_reason')!r} body={str(body)[:300]}"
        )
    return "".join(text_parts)


def parse_candidates(raw: str) -> list[Candidate]:
    payload: dict[str, Any] = json.loads(_strip_json_fences(raw))
    if "candidates" not in payload or not isinstance(payload["candidates"], list):
        raise ValueError("expected top-level 'candidates' list")
    out: list[Candidate] = []
    for item in payload["candidates"]:
        out.append(
            Candidate(
                probability=float(item["probability"]),
                concept=cast(Concept, item["concept"]),
            )
        )
    if not out:
        raise ValueError("zero candidates in response")
    return out


async def translate(
    tokens: Iterable[dict[str, Any]],
    summary: dict[str, Any],
    audio_hash: str,
    session_id: str = "default",
) -> TranslationResult:
    """Full translation: seeded style pick -> API call -> VS parse -> diverse pick -> archive."""
    seed = _seed_from_hash(audio_hash)
    triplet = style_cards.pick_triplet(seed=seed)
    recipe = recipes.pick_recipe(seed=seed + 1)
    recent = archive.recent_summaries(session_id, n=5)

    system_prompt = prompts.SYSTEM_PROMPT
    user_prompt = prompts.build_user_prompt(
        tokens=list(tokens),
        summary=summary,
        audio_hash=audio_hash,
        style=triplet,
        recipe=recipe,
        recent_concept_summaries=recent,
    )

    logger.info(
        f"translate: hash={audio_hash} art={triplet['art']['name']} "
        f"mechanic={triplet['mechanic']['name']} mood={triplet['mood']['name']} "
        f"recipe={recipe['name']} model={settings.API_TRANSLATE_MODEL} "
        f"avoid={len(recent)}"
    )
    raw = await _call_claude(system_prompt, user_prompt)
    candidates = parse_candidates(raw)
    chosen, score = _select(candidates, recent)

    cell: tuple[str, str, str] = (
        triplet["art"]["name"],
        triplet["mechanic"]["name"],
        triplet["mood"]["name"],
    )
    chosen_summary = f"{chosen['concept']['title']} — {chosen['concept']['tagline']}"
    archive.record(session_id, cell, chosen_summary, audio_hash)

    return TranslationResult(
        chosen=chosen["concept"],
        chosen_probability=chosen["probability"],
        chosen_score=score,
        candidates=candidates,
        style_triplet=triplet,
        visual_recipe=recipe["name"],
        avoided_summaries=recent,
    )
