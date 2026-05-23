"""Translation orchestrator — Verbalized Sampling + diversity-weighted pick.

Calls Claude via the configured Anthropic Messages API proxy (aipaibox by
default). This is a separate path from the legacy SDK so it doesn't compete
with the user's interactive Claude Code window for Max-plan quota — same
reason the game generator switched in PR #10.

We **stream** the API response. The translate output is small (~500 tokens of
JSON for 3 candidates), but streaming buys two real wins over the previous
non-streaming POST:

  • Per-event idle bound (no bytes for ``_IDLE_TIMEOUT_S`` → stale) instead of
    a single all-or-nothing 120 s ceiling. When the upstream channel is slow
    but alive (drip-feeding bytes), we keep waiting; when it has actually
    stalled, we know in seconds instead of two minutes.
  • Clean integration with the retry loop. ``httpx.ReadTimeout`` now feeds
    into the same transient-failure budget that already catches 502/503/504,
    so a busy aipaibox channel doesn't 502 the user on the first try.

What this layer adds beyond the LLM call:
  1. **Triplet picking with archive-aware down-weighting** — cards already
     used in this session are softer-weighted so a session of 8 generations
     naturally explores more of the pool.
  2. **Audio → game parameter derivation** — the bark's rhythm, intensity,
     and entropy are mapped to concrete gameplay knobs (spawn interval,
     concurrency cap, escalation rate, randomness) so the same mechanic
     plays differently for different barks instead of just changing flavour.
  3. **Verbalized Sampling diversity pick** — among the candidates the model
     returns, choose the one with the highest probability × novelty.
"""

from __future__ import annotations

import asyncio
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

# Total budget per single attempt. Generous: we expect 30-60 s on a healthy
# channel and want headroom for slow channels. Crossing this almost never
# happens in practice because the read bound (below) trips first when the
# upstream stalls.
_REQUEST_TIMEOUT_S = 240.0

# Per-event idle bound. As long as the model is actively streaming bytes we
# keep waiting; when bytes stop, this is how long we tolerate silence before
# treating the call as stalled. Translate output is short, so 60 s of pure
# silence is decisive.
_IDLE_TIMEOUT_S = 60.0

# Connection setup bound (DNS + TCP + TLS). aipaibox is sometimes slow to
# allocate a channel; this still has to fit inside the overall budget.
_CONNECT_TIMEOUT_S = 30.0


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


# HTTP status codes worth retrying. 502 = bad gateway, 503 = service
# unavailable / "no available channel" from the aipaibox proxy (real prod
# pattern: cheap-tier channels saturate for seconds at a time), 504 = upstream
# timeout. None of these are caused by our payload, so a retry has a real
# chance of succeeding within seconds.
_RETRYABLE_STATUS = frozenset({502, 503, 504})

# Backoff schedule between attempts (in seconds). Override at module-level
# in tests for instant runs.
_RETRY_BACKOFFS_S: tuple[float, ...] = (0.8, 2.5)


class _TransientUpstreamError(Exception):
    """Internal signal: upstream had a transient failure worth retrying."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


async def _stream_messages(
    payload: dict[str, Any], headers: dict[str, str]
) -> str:
    """Stream a single Messages API call, return the concatenated assistant text.

    Maps every failure mode into one of three outcomes:
      • clean text on success
      • ``_TransientUpstreamError`` for anything the retry loop should retry
        (5xx, ReadTimeout, ConnectError, stream-level ``overloaded_error``)
      • ``RuntimeError`` / ``RateLimitedError`` for terminal failures
        (4xx, empty-stream, malformed stream)
    """
    timeout = httpx.Timeout(
        _REQUEST_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S, read=_IDLE_TIMEOUT_S
    )
    url = f"{settings.API_BASE_URL}/v1/messages"
    text_parts: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                if resp.status_code == 429:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[
                        :300
                    ]
                    raise RateLimitedError(
                        f"translate API rate-limited (HTTP 429): {body}",
                        resets_at=None,
                    )
                if resp.status_code in _RETRYABLE_STATUS:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[
                        :200
                    ]
                    raise _TransientUpstreamError(
                        f"HTTP {resp.status_code}: {body}",
                        status=resp.status_code,
                    )
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[
                        :300
                    ]
                    raise RuntimeError(
                        f"translate API HTTP {resp.status_code}: {body}"
                    )

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[len("data: ") :].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug(f"translate: malformed SSE line: {raw[:200]}")
                        continue
                    etype = event.get("type")
                    if etype == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text_parts.append(delta.get("text", ""))
                    elif etype == "error":
                        err = event.get("error") or {}
                        if err.get("type") == "overloaded_error":
                            # Same family as 503: cheap-tier saturation.
                            raise _TransientUpstreamError(
                                f"stream overloaded: {err.get('message', '?')}"
                            )
                        raise RuntimeError(f"translate stream error: {err}")
    except httpx.TimeoutException as exc:
        # ReadTimeout = ``_IDLE_TIMEOUT_S`` of silence after some progress
        # (or before the stream even started). ConnectTimeout = couldn't
        # reach the proxy. Either way, retry has a real chance because a
        # fresh channel may be allocated on the next try.
        raise _TransientUpstreamError(
            f"{type(exc).__name__} "
            f"(idle bound {_IDLE_TIMEOUT_S:.0f}s, total bound {_REQUEST_TIMEOUT_S:.0f}s)"
        ) from exc
    except httpx.ConnectError as exc:
        detail = str(exc) or type(exc).__name__
        raise _TransientUpstreamError(f"ConnectError: {detail}") from exc

    text = "".join(text_parts)
    if not text:
        # Explicit failure beats a downstream JSONDecodeError on "" — the
        # stream completed but produced zero text deltas (often: only
        # tool_use blocks, or empty content from a content-filter trip).
        raise RuntimeError(
            "translate API returned empty stream (no text deltas before end)"
        )
    return text


async def _call_claude_once(system_prompt: str, user_prompt: str) -> str:
    """Single streaming attempt — see ``_call_claude`` for the retrying wrapper."""
    payload = {
        "model": settings.API_TRANSLATE_MODEL,
        "max_tokens": settings.API_TRANSLATE_MAX_OUTPUT_TOKENS,
        "stream": True,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": settings.API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    return await _stream_messages(payload, headers)


async def _call_claude(system_prompt: str, user_prompt: str) -> str:
    """Resilient streaming Messages API call. Retries on transient failures.

    Retried (1 initial attempt + up to ``len(_RETRY_BACKOFFS_S)`` more):
      • httpx.TimeoutException — ReadTimeout (idle) / ConnectTimeout / total
        budget. The upstream is alive elsewhere; a fresh channel often
        unblocks it.
      • httpx.ConnectError after transport's network-layer retries.
      • HTTP 502 / 503 / 504 — proxy / channel saturation.
      • Stream-level ``overloaded_error`` events.

    NOT retried:
      • 4xx (except 429 → RateLimitedError) — our payload is at fault.
      • Empty response with no text deltas — content-level issue.
      • Stream errors other than overloaded — model surfaced a real problem.
    """
    if not settings.API_KEY:
        raise RuntimeError(
            "BARK_API_KEY is not set. Set it in backend/.env before calling translate."
        )

    last_transient: _TransientUpstreamError | None = None
    for attempt in range(1, len(_RETRY_BACKOFFS_S) + 2):
        try:
            return await _call_claude_once(system_prompt, user_prompt)
        except _TransientUpstreamError as exc:
            last_transient = exc
            if attempt > len(_RETRY_BACKOFFS_S):
                break  # budget exhausted, fall through to raise
            delay = _RETRY_BACKOFFS_S[attempt - 1]
            logger.warning(
                f"translate: transient upstream failure on attempt {attempt} "
                f"({exc}); retrying in {delay}s"
            )
            await asyncio.sleep(delay)

    assert last_transient is not None
    raise RuntimeError(
        f"translate upstream busy after {len(_RETRY_BACKOFFS_S) + 1} attempts "
        f"(last: {last_transient}). Try again in a few seconds."
    ) from last_transient


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
