"""One-off maintenance: remove husk game dirs (a dir with no game.html).

Husks are left by generations that failed before writing game.html. The
runtime cleanup in routes/game.py prevents new husks; this sweeps the
pre-existing backlog.

    uv run python -m bark_to_game.generate.maintenance          # dry-run
    uv run python -m bark_to_game.generate.maintenance --apply  # delete
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from bark_to_game.paths import GENERATED_GAMES_DIR


def sweep_husks(games_dir: Path | None = None, *, dry_run: bool = False) -> list[str]:
    """Return the names of husk dirs (a subdir with no game.html). Removes
    them unless dry_run. Non-directory entries are ignored."""
    root = games_dir or GENERATED_GAMES_DIR
    removed: list[str] = []
    if not root.exists():
        return removed
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "game.html").exists():
            continue
        removed.append(child.name)
        if not dry_run:
            shutil.rmtree(child, ignore_errors=True)
    return removed


def main() -> None:
    apply = "--apply" in sys.argv
    removed = sweep_husks(dry_run=not apply)
    header = "DELETED" if apply else "DRY-RUN (pass --apply to delete)"
    print(f"{header}: {len(removed)} husk dir(s) under {GENERATED_GAMES_DIR}")
    for name in removed:
        print(f"  {name}")


if __name__ == "__main__":
    main()
