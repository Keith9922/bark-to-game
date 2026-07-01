"""Runtime configuration.

Loaded once at import. Values come from environment variables, optionally
seeded from a ``.env`` file at the backend root. Keep secrets out of git;
``.env`` is in ``.gitignore``, ``.env.example`` is the template.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env from the backend root (one dir above this package).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env", override=False)

GeneratorMode = Literal["api", "sdk"]


def _generator_mode() -> GeneratorMode:
    raw = os.getenv("BARK_GENERATOR_MODE", "api").strip().lower()
    if raw not in ("api", "sdk"):
        raise ValueError(f"BARK_GENERATOR_MODE must be 'api' or 'sdk', got {raw!r}")
    return raw  # type: ignore[return-value]


# Which generator backend serves /api/game/generate.
#   "api": direct Anthropic Messages API via configured base URL + key
#   "sdk": legacy claude-agent-sdk subprocess (uses Claude Max plan auth)
GENERATOR_MODE: GeneratorMode = _generator_mode()

# Anthropic Messages API proxy. Default points at the aipaibox channel the
# project was configured with; override per-environment via .env.
API_BASE_URL: str = os.getenv("BARK_API_BASE_URL", "https://api.aipaibox.com").rstrip("/")

# API key for the proxy. Must be set when GENERATOR_MODE="api"; raises at
# call time (not import time) so SDK-only deployments can omit it.
API_KEY: str | None = os.getenv("BARK_API_KEY") or None

# Model name. Defaults to the latest Opus — best for code-output-dense
# game generation; thinking variants add latency without helping output quality.
API_MODEL: str = os.getenv("BARK_API_MODEL", "claude-opus-4-7")

# Hard cap on tokens per generation. Single-file games run 28-33 KB of HTML
# (~10-15k tokens with dense JS); 32000 leaves 2-3x headroom so truncation
# (the dominant husk cause) essentially disappears. Bump via .env if needed.
API_MAX_OUTPUT_TOKENS: int = int(os.getenv("BARK_API_MAX_OUTPUT_TOKENS", "32000"))

# Translate stage (token sequence -> 5 game concept candidates) is much
# lighter than game generation — ~700 output tokens of JSON. Defaults to a
# cheap+fast model so we don't burn Opus dollars on conceptual brainstorming.
# Override with BARK_API_TRANSLATE_MODEL in .env if Sonnet's concepts feel weak.
API_TRANSLATE_MODEL: str = os.getenv("BARK_API_TRANSLATE_MODEL", "claude-sonnet-4-6")

# Cap on tokens for translate JSON output. After PR #29 each candidate
# carries 11 fields (added onboarding_hint, escalation_moment, replay_hook),
# so 5 candidates ≈ 5 × ~300 tokens ≈ 1500 tokens of body. 4096 was getting
# tight on the longer candidates and forced truncation → invalid JSON. 8192
# gives comfortable headroom without inflating cost.
API_TRANSLATE_MAX_OUTPUT_TOKENS: int = int(
    os.getenv("BARK_API_TRANSLATE_MAX_OUTPUT_TOKENS", "8192")
)
