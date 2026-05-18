"""Loader for the game-assets playbook (markdown the generator adapts from).

The playbook has two layers:

  1. **Shared core** — universal patterns every generated game needs:
     scaffold, input plumbing, Web Audio, canvas helpers, always-visible HUD,
     onboarding affordance, escalation banner, audio-DNA-driven difficulty
     curve. This is ALWAYS injected into CLAUDE.md.

  2. **Mechanic sketches** — one short code skeleton per mechanic
     (`### Catch (...)`, `### Snake (...)`, ...). Only the ONE matching the
     chosen mechanic is injected; the rest stay on disk.

Why slice: as the mechanic pool grows, injecting every sketch would push the
``generate`` input from ~6 k to ~15 k+ tokens, eating output budget and
nudging requests toward the timeout ceiling. Slicing keeps each generation's
input roughly constant regardless of pool size.
"""

from __future__ import annotations

import re
from functools import lru_cache

from bark_to_game.paths import GAME_ASSETS_DIR

# Anchor strings that split the markdown into header / sketches / epilogue.
_MECHANIC_START = "\n---\n\n# Common mechanics"
_MECHANIC_END = "\n---\n\n## Game-over loop"


def _norm(name: str) -> str:
    """Normalise a mechanic name so JSON ``charge_release`` matches playbook ``Charge-release``."""
    return re.sub(r"[\s_\-]+", "", name).lower()


@lru_cache(maxsize=1)
def _read_full() -> str:
    return (GAME_ASSETS_DIR / "playbook.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _split() -> tuple[str, dict[str, str], str]:
    md = _read_full()
    h_end = md.find(_MECHANIC_START)
    e_start = md.find(_MECHANIC_END)
    if h_end == -1 or e_start == -1:
        # Lost the dividers — degrade by returning the whole thing as header
        # so generation still has the shared core.
        return md, {}, ""

    header = md[:h_end].rstrip()
    sketches_block = md[h_end:e_start]
    epilogue = md[e_start:].lstrip("\n-").lstrip()

    # Each sketch starts with ``### Name (...)``. Split on the newline before
    # the next ``### `` heading.
    sketches: dict[str, str] = {}
    for chunk in re.split(r"\n(?=### )", sketches_block):
        m = re.match(r"### ([A-Za-z][\w\- ]*?)(?:\s*\(|\s*\n)", chunk)
        if not m:
            continue
        sketches[_norm(m.group(1))] = chunk.strip()
    return header, sketches, epilogue


def load_for(mechanic_name: str | None = None) -> str:
    """Return shared core + the sketch matching ``mechanic_name`` (if any).

    When ``mechanic_name`` is None or unknown, returns shared core + epilogue
    only — the LLM still has the universal patterns and writes the mechanic
    from scratch.
    """
    header, sketches, epilogue = _split()
    if not mechanic_name:
        return f"{header}\n\n---\n\n{epilogue}".rstrip() + "\n"

    sketch = sketches.get(_norm(mechanic_name))
    if sketch is None:
        return f"{header}\n\n---\n\n{epilogue}".rstrip() + "\n"

    return (
        f"{header}\n\n---\n\n"
        f"# Sketch for THIS game's mechanic — adapt freely, don't paste verbatim\n\n"
        f"{sketch}\n\n---\n\n{epilogue}"
    ).rstrip() + "\n"


@lru_cache(maxsize=1)
def load() -> str:
    """Legacy: full playbook. Kept for any callers that haven't migrated yet."""
    return _read_full()
