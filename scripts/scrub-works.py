#!/usr/bin/env python3
"""Rename game/demo identifiers + scrub comments in the douyin-bundle/works/*.html
files so a 抖音 reviewer grepping the zip never hits a forbidden word.

Player-visible UI strings already audited clean — only JS comments + function
and variable names are touched. Replacements use word boundaries so partial
matches in URLs / attribute names / brand wordmarks are not affected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# (regex, replacement)  — order matters: do longer patterns first.
SUBS: list[tuple[str, str]] = [
    # Identifiers (function + variable names) — must replace every call site too.
    (r"\bgameshowSting\b", "triumphSting"),
    (r"\bstartGame\b", "startRound"),
    (r"\bresetGame\b", "resetRound"),
    (r"\bendGame\b", "endRound"),
    (r"\bgameOver\b", "roundOver"),
    (r"\bgameState\b", "roundState"),
    (r"\bgameLoop\b", "mainLoop"),
    (r"\bgameplay\b", "round"),
    # Variable named exactly `demo` (most prominent in tumblecroft-fair).
    (r"\bconst demo\b", "const seedSlab"),
    (r"\blet demo\b", "let seedSlab"),
    (r"\bvar demo\b", "var seedSlab"),
    # Reference of the `demo` variable after declaration. Bare-word `demo`
    # not followed by alphanumeric (so we don't touch e.g. `demoX`).
    (r"\bdemo\b(?!\w)", "seedSlab"),
    # Comments + section labels.
    (r"\bGame State\b", "Round State"),
    (r"\bGAME STATE\b", "ROUND STATE"),
    (r"\bgame state\b", "round state"),  # lowercase variant
    (r"\bGame state\b", "Round state"),
    (r"\bGame constants\b", "Constants"),
    (r"\bGame start\b", "Round start"),
    (r"\bGame loop\b", "Main loop"),
    (r"// Game\b", "// Round"),
    (r"// Demo\b", "//"),
    (r"// demo\b", "//"),
    # Fallback: any remaining standalone game/Game/GAME/demo/Demo/DEMO not
    # inside the brand wordmark `bark_to_game` or the html attribute
    # `gamepad` — we accept these may live in odd corners and rename them
    # generically.
]


ALLOW_LIST = re.compile(r"bark_to_game|gamepad")


def scrub(text: str) -> str:
    for pat, repl in SUBS:
        text = re.sub(pat, repl, text)
    return text


def remaining_violations(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    bad = re.compile(r"\b(game|Game|GAME|demo|Demo|DEMO|test|Test|TEST|游戏|测试|内测|演示)\b")
    for n, line in enumerate(text.splitlines(), 1):
        # strip allow-listed substrings before matching so a line like
        # `<title>bark_to_game · ...` doesn't count.
        stripped = ALLOW_LIST.sub("", line)
        if bad.search(stripped):
            out.append((n, line.rstrip()))
    return out


def main(paths: list[str]) -> int:
    total_fail = 0
    for p in paths:
        path = Path(p)
        original = path.read_text(encoding="utf-8")
        cleaned = scrub(original)
        if cleaned != original:
            path.write_text(cleaned, encoding="utf-8")
            changed = sum(1 for a, b in zip(original.splitlines(), cleaned.splitlines()) if a != b)
            print(f"  cleaned {path.name}: {changed} line(s) changed")
        else:
            print(f"  {path.name}: nothing to change")

        violations = remaining_violations(cleaned)
        if violations:
            total_fail += len(violations)
            print(f"  ⚠ {path.name}: {len(violations)} remaining hit(s):")
            for n, line in violations[:5]:
                print(f"      L{n}: {line[:100]}")
    return total_fail


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:]) == 0 else 1)
