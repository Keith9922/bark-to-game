"""Translation orchestrator — Verbalized Sampling + diversity-weighted pick.

Calls Claude via the configured Anthropic Messages API proxy (aipaibox by
default). This is a separate path from the legacy SDK so it doesn't compete
with the user's interactive Claude Code window for Max-plan quota — same
reason the game generator switched in PR #10.

Translate output is small (~700 tokens of JSON) so we use a single
non-streaming POST instead of the streaming flow `_api_backend.py` uses
for the long game generation.

What this layer adds beyond the LLM call:
  1. **Triplet picking with archive-aware down-weighting** — cards already
     used in this session are softer-weighted so a session of 8 generations
     naturally explores more of the pool.
  2. **Audio → game parameter derivation** — the bark's rhythm, intensity,
     and entropy are mapped to concrete gameplay knobs (spawn interval,
     concurrency cap, escalation rate, randomness) so the same mechanic
     plays differently for different barks instead of just changing flavour.
  3. **Verbalized Sampling diversity pick** — among the 5 candidates the
     model returns, choose the one with the highest probability × novelty.
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
    onboarding_hint: str
    escalation_moment: str
    replay_hook: str
    visual_summary: str
    audio_summary: str


class Candidate(TypedDict):
    probability: float
    concept: Concept


class GameParams(TypedDict):
    tempo: str
    density: str
    intensity: str
    variability: str
    spawn_interval_ms: int
    max_concurrent: int
    escalation_per_min: float
    randomness_pct: int


class TranslationResult(TypedDict):
    chosen: Concept
    chosen_probability: float
    chosen_score: float
    candidates: list[Candidate]
    style_triplet: style_cards.StyleTriplet
    visual_recipe: str  # recipe name
    game_params: GameParams
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


# --- audio → gameplay knob mapping -----------------------------------------

# Bark vocabulary the audio pipeline emits (see audio/pipeline.py + tokens.py)
# Rhythm    : STACCATO | TRIPLET | SPACED | SPARSE
# Mood      : AGITATED | MELANCHOLY | PLAYFUL | STEADY
# Token-level intensity: SOFT | NORMAL | LOUD
# Entropy   : 0.0 (uniform) → 1.0 (very varied)

_TEMPO_FROM_RHYTHM = {
    "STACCATO": "frantic",
    "TRIPLET": "fast",
    "SPACED": "medium",
    "SPARSE": "slow",
}

# Concrete numbers per tempo band — these are what land in CLAUDE.md so the
# game-generator has actual integers to use as spawn rates / wave timings.
_TEMPO_KNOBS = {
    "slow":    {"spawn_interval_ms": 1500, "escalation_per_min": 1.20},
    "medium":  {"spawn_interval_ms": 1000, "escalation_per_min": 1.35},
    "fast":    {"spawn_interval_ms":  600, "escalation_per_min": 1.55},
    "frantic": {"spawn_interval_ms":  350, "escalation_per_min": 1.80},
}

_DENSITY_MAX_CONCURRENT = {"sparse": 4, "moderate": 8, "dense": 14}
_VARIABILITY_RANDOMNESS_PCT = {"steady": 10, "shifting": 30, "wild": 60}


def _derive_game_params(
    tokens: list[dict[str, Any]],
    summary: dict[str, Any],
) -> GameParams:
    """Map bark features → gameplay knobs.

    The mapping is intentionally simple and explainable: a STACCATO bark
    gives a frantic spawn rate; a SPARSE bark gives a slow one. Entropy
    drives the spawn-pattern randomness. Intensity (count of LOUD tokens)
    drives the escalation rate. This is what makes the same mechanic
    actually feel different across barks instead of just changing colours.
    """
    rhythm = str(summary.get("rhythm") or "SPACED").upper()
    tempo = _TEMPO_FROM_RHYTHM.get(rhythm, "medium")

    # Density: token count + entropy decide. Lots of varied tokens → dense.
    n = len(tokens)
    entropy = float(summary.get("entropy") or 0.0)
    if n >= 8 and entropy >= 0.6:
        density = "dense"
    elif n >= 4:
        density = "moderate"
    else:
        density = "sparse"

    # Intensity: fraction of LOUD tokens in the segment list.
    loud = sum(1 for t in tokens if str(t.get("intensity", "")).upper() == "LOUD")
    loud_ratio = loud / max(n, 1)
    if loud_ratio >= 0.5:
        intensity = "harsh"
    elif loud_ratio >= 0.2:
        intensity = "firm"
    else:
        intensity = "gentle"

    # Variability: pure entropy bucket.
    if entropy >= 0.66:
        variability = "wild"
    elif entropy >= 0.33:
        variability = "shifting"
    else:
        variability = "steady"

    knobs = _TEMPO_KNOBS[tempo]
    return GameParams(
        tempo=tempo,
        density=density,
        intensity=intensity,
        variability=variability,
        spawn_interval_ms=knobs["spawn_interval_ms"],
        max_concurrent=_DENSITY_MAX_CONCURRENT[density],
        escalation_per_min=knobs["escalation_per_min"],
        randomness_pct=_VARIABILITY_RANDOMNESS_PCT[variability],
    )


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
    token_list = list(tokens)
    seed = _seed_from_hash(audio_hash)

    occupied = archive.occupied_cells(session_id)
    triplet = style_cards.pick_triplet(seed=seed, occupied_cells=occupied)
    recipe = recipes.pick_recipe(seed=seed + 1)
    recent = archive.recent_summaries(session_id, n=5)
    game_params = _derive_game_params(token_list, summary)

    system_prompt = prompts.SYSTEM_PROMPT
    user_prompt = prompts.build_user_prompt(
        tokens=token_list,
        summary=summary,
        audio_hash=audio_hash,
        style=triplet,
        recipe=recipe,
        game_params=cast(dict[str, Any], game_params),
        recent_concept_summaries=recent,
    )

    logger.info(
        f"translate: hash={audio_hash} art={triplet['art']['name']} "
        f"mechanic={triplet['mechanic']['name']} mood={triplet['mood']['name']} "
        f"recipe={recipe['name']} tempo={game_params['tempo']} "
        f"density={game_params['density']} occupied={len(occupied)} "
        f"model={settings.API_TRANSLATE_MODEL} avoid={len(recent)}"
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
        game_params=game_params,
        avoided_summaries=recent,
    )
