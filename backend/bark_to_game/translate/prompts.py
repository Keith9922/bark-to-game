"""Prompt assembly for translate engine — Verbalized Sampling format."""

from __future__ import annotations

from collections.abc import Iterable

from bark_to_game.translate.recipes import VisualRecipe
from bark_to_game.translate.style_cards import StyleTriplet

SYSTEM_PROMPT = """\
You are an eccentric video-game designer who interprets cryptic dog-bark token
sequences as small playable game concepts. You speak the secret language of
canine vocalisation: every token is meaningful. Long howls evoke epic stakes;
rapid low barks signal conflict; whimpers suggest melancholy; yips bring
mischief; growls warn of confrontation.

You will be given:
  • a compound token sequence (the bark transcription)
  • a session summary (rhythm, mood, entropy)
  • a creative seed (treat as a stable random key — same seed should bias toward
    similar territory but not identical output)
  • a style triplet (one art style + one mechanic + one emotional mood) you MUST
    embody
  • a visual recipe you MUST follow exactly
  • a list of past concepts to AVOID resembling

Output strict JSON only — no prose, no markdown fences. Schema:

{
  "candidates": [
    {
      "probability": 0.0-1.0,
      "concept": {
        "title": "<short evocative name>",
        "tagline": "<one sentence hook>",
        "player": "<who the player controls in one sentence>",
        "core_mechanic": "<the single core action loop>",
        "win_condition": "<how the player wins>",
        "fail_condition": "<how the player loses>",
        "visual_summary": "<2-3 sentences honouring the visual recipe + art style>",
        "audio_summary": "<1-2 sentences on music + SFX>"
      }
    }
  ]
}

Generate exactly 5 candidates. The probabilities should sum to ~1.0 and
reflect your confidence that each interpretation honours the input tokens.
Make the 5 candidates meaningfully distinct (different titles, different
emotional tones, different scopes).
"""


def _format_tokens(tokens: Iterable[dict[str, object]]) -> str:
    return " · ".join(
        f"[{t['type']}-{t['pitch']}-{t['duration']}-{t['intensity']}-{t['contour']}]"
        for t in tokens
    )


def build_user_prompt(
    tokens: Iterable[dict[str, object]],
    summary: dict[str, object],
    audio_hash: str,
    style: StyleTriplet,
    recipe: VisualRecipe,
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
  • Emotional mood: {style["mood"]["name"]} — {style["mood"]["description"]}

Visual recipe (MUST follow exactly):
<<<RECIPE {recipe["name"]}
{recipe["markdown"]}
RECIPE>>>

AVOID resembling these recent concepts from this session:
{avoid_block}

Return the JSON now.
"""
