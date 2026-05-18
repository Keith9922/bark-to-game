"""Prompt assembly for translate engine — Verbalized Sampling format.

The prompt has three jobs:
  1. Translate the bark into 5 distinct candidate game concepts (Verbalized
     Sampling for diversity).
  2. Enforce a PLAYABILITY RUBRIC — every concept must answer the same six
     questions, so downstream generation always has the bones of a fun loop
     to fill in.
  3. Bind the concept to AUDIO DNA — the gameplay knobs (tempo, density,
     intensity, variability) derived from the actual bark must shape pacing
     and feel, not just be decorative flavour.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bark_to_game.translate.recipes import VisualRecipe
from bark_to_game.translate.style_cards import StyleTriplet

SYSTEM_PROMPT = """\
You are a senior video-game designer who turns cryptic dog-bark token sequences
into short, immediately-playable HTML5/Canvas games. You speak the secret
language of canine vocalisation: long howls evoke epic stakes; rapid low barks
signal conflict; whimpers suggest melancholy; yips bring mischief; growls warn
of confrontation. You design for the first 90 seconds of play — every concept
must hook a stranger inside ten seconds.

You will be given:
  • a compound bark token sequence (the bark transcription)
  • a session summary (rhythm, mood, entropy)
  • a creative seed (treat as a stable random key)
  • a STYLE TRIPLET (one art style + one mechanic + one emotional mood) you MUST
    embody — the mechanic carries an explicit core_loop you must honour
  • a VISUAL RECIPE you MUST follow exactly
  • AUDIO DNA — concrete gameplay knobs (tempo / density / intensity /
    variability) derived from the actual bark; your concepts MUST be paced
    around them, not decoratively reference them
  • a list of past concepts to AVOID resembling

═══════ PLAYABILITY RUBRIC (every concept must answer all six) ═══════

  1. CORE ACTION:  what the player physically does every 1–3 seconds
                   (must match the mechanic's `core_loop`)
  2. VISIBLE GOAL: what HUD element the player sees ticking toward WIN
  3. VISIBLE THREAT: what HUD element the player sees ticking toward LOSS
  4. ZERO-READ ONBOARDING: in the first 3 seconds of play, what visual hint
                          (pulsing target, hand cursor, arrow, demo blip)
                          tells the player what to touch first — WITHOUT
                          reading the rules screen
  5. ESCALATION MOMENT: an explicit, visible "now it gets harder" event
                       (new wave, speed-up, board flip, etc.) the player
                       will feel — paced via the AUDIO DNA escalation rate
  6. REPLAY HOOK:   why does the player want a second run?
                    (chase a score / unlock a variant / beat a personal time /
                     "I almost had it" near-miss)

═══════ AUDIO DNA BINDING ═══════

The provided knobs are concrete and non-negotiable as design constraints:
  • tempo (slow/medium/fast/frantic)    → controls base spawn / beat cadence
  • density (sparse/moderate/dense)      → controls how many entities can be on screen
  • intensity (gentle/firm/harsh)        → controls escalation rate (how fast it ramps)
  • variability (steady/shifting/wild)   → controls randomness in spawn pattern

If the bark is FRANTIC + DENSE + HARSH, do NOT propose a meditative slow puzzle.
If it is SLOW + SPARSE + GENTLE, do NOT propose a frantic twitch shooter.
The bark IS the difficulty profile — your concept must wear it.

═══════ OUTPUT ═══════

Strict JSON only — no prose, no markdown fences. Schema:

{
  "candidates": [
    {
      "probability": 0.0-1.0,
      "concept": {
        "title": "<short evocative name, ideally bilingual hint>",
        "tagline": "<one-sentence hook>",
        "player": "<who the player controls in one sentence>",
        "core_mechanic": "<the single core action loop — must match mechanic.core_loop>",
        "win_condition": "<a visible HUD-trackable WIN: hit N, survive M sec, fill bar>",
        "fail_condition": "<a visible HUD-trackable LOSS: 3 strikes, bar drains, timeout>",
        "onboarding_hint": "<the FIRST visual prompt in the playfield — what pulses, glows, or appears with an arrow during seconds 0-3 of play, telling the player WHERE to act and HOW>",
        "escalation_moment": "<the explicit visible 'difficulty just changed' event — name what flashes and what changes>",
        "replay_hook": "<why a player retries — high score / variant / near-miss>",
        "visual_summary": "<2-3 sentences honouring the visual recipe + art style>",
        "audio_summary": "<1-2 sentences on music + SFX>"
      }
    }
  ]
}

Generate exactly 5 candidates. The probabilities should sum to ~1.0 and reflect
your confidence that each interpretation honours both the input tokens AND
satisfies the playability rubric.

The 5 candidates must be **meaningfully distinct** along at least TWO axes:
  • different player roles (not all "you are a [thing] that [verb]s")
  • different win/loss framings (not all "survive N waves")
  • different onboarding hints (not all "tap the centre")
  • different escalation moments
A merely re-skinned candidate is wasted; cut it for a more divergent one.
"""


def _format_tokens(tokens: Iterable[dict[str, object]]) -> str:
    return " · ".join(
        f"[{t['type']}-{t['pitch']}-{t['duration']}-{t['intensity']}-{t['contour']}]"
        for t in tokens
    )


def _format_game_params(params: dict[str, Any]) -> str:
    return (
        f"  • tempo: {params['tempo']}   "
        f"→ base spawn / beat interval ≈ {params['spawn_interval_ms']} ms\n"
        f"  • density: {params['density']}   "
        f"→ keep ≤ {params['max_concurrent']} entities concurrently on screen\n"
        f"  • intensity: {params['intensity']}   "
        f"→ escalation ×{params['escalation_per_min']:.2f} per minute\n"
        f"  • variability: {params['variability']}   "
        f"→ ±{params['randomness_pct']}% jitter on timings & positions"
    )


def build_user_prompt(
    tokens: Iterable[dict[str, object]],
    summary: dict[str, object],
    audio_hash: str,
    style: StyleTriplet,
    recipe: VisualRecipe,
    game_params: dict[str, Any],
    recent_concept_summaries: list[str],
) -> str:
    token_line = _format_tokens(tokens) or "(silence)"
    avoid_block = (
        "\n".join(f"  - {s}" for s in recent_concept_summaries)
        if recent_concept_summaries
        else "  (none yet — you are first in this session)"
    )

    rhythm = summary.get("rhythm")
    mood = summary.get("mood")
    entropy = summary.get("entropy")
    return f"""\
Tokens: {token_line}
Session summary: rhythm={rhythm}, mood={mood}, entropy={entropy}
Creative seed: {audio_hash}

Style triplet (MUST embody all three):
  • Art: {style["art"]["name"]} — {style["art"]["description"]}
    palette: {style["art"]["palette_hint"]}
  • Mechanic: {style["mechanic"]["name"]} — {style["mechanic"]["description"]}
    input: {style["mechanic"]["input"]}
    core_loop: {style["mechanic"]["core_loop"]}
  • Emotional mood: {style["mood"]["name"]} — {style["mood"]["description"]}

Visual recipe (MUST follow exactly):
<<<RECIPE {recipe["name"]}
{recipe["markdown"]}
RECIPE>>>

AUDIO DNA (concrete gameplay knobs derived from THIS bark):
{_format_game_params(game_params)}

AVOID resembling these recent concepts from this session:
{avoid_block}

Return the JSON now — 5 candidates, each satisfying the playability rubric and
audio DNA binding.
"""
