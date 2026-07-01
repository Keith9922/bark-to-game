# Phase 1 · Milestone D — Backend Generation Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the ~33% "husk" generation failures (dir with only `CLAUDE.md`, no `game.html`) by detecting `max_tokens` truncation, raising the output cap, retrying transient failures, and cleaning up husk directories.

**Architecture:** All changes are in the backend `generate` + `routes` layers. The direct-API backend (`_api_backend.py`) gains truncation detection (reads `stop_reason` from the streaming `message_delta` event). The job runner (`routes/game.py::_run_job`) gains a bounded retry loop and per-attempt husk cleanup. A standalone maintenance module sweeps pre-existing husks.

**Tech Stack:** Python 3.13, FastAPI, `httpx` (streaming), pytest (async), `uv`. Generator backend is `api` mode (`settings.GENERATOR_MODE`, default `"api"`).

## Global Constraints

- Python: fully type-hinted, `mypy` clean. No new runtime dependencies.
- Single responsibility; KISS; solve at the root (no patch-on-patch).
- Both generator backends raise the SAME error types (`RateLimitedError`, `GenerationStalledError`, and the new `GenerationTruncatedError`) so `routes/game.py` stays backend-agnostic.
- `stop_reason` in Anthropic streaming lives in the `message_delta` event at `delta.stop_reason` (verified: `tests/test_api_backend.py::_sse_body` emits `{"type":"message_delta","delta":{"stop_reason":"end_turn"}}`).
- Tests run from `backend/` via `uv run pytest`. Async tests use the existing (already-configured) async mode — follow the `async def test_...` pattern already in `tests/test_api_backend.py`.
- Never delete a game dir that contains `game.html`.

---

## Task 1: Truncation detection + clearer model error

Detect `stop_reason == "max_tokens"` during streaming and surface it as a distinct `GenerationTruncatedError`; raise the output cap to 32000; give a clear error when the proxy rejects the model id.

**Files:**
- Modify: `backend/bark_to_game/generate/_common.py` (add error class after `GenerationStalledError`, ~line 34-35)
- Modify: `backend/bark_to_game/generate/generator.py` (import + `__all__`, lines 19-31)
- Modify: `backend/bark_to_game/generate/_api_backend.py` (`_handle_event` 439-458; `_stream_messages` 337-405; `generate_via_api` 288-298; import 31-36)
- Modify: `backend/bark_to_game/settings.py` (`API_MAX_OUTPUT_TOKENS`, line 49)
- Test: `backend/tests/test_api_backend.py`

**Interfaces:**
- Produces: `GenerationTruncatedError(RuntimeError)` in `_common.py`, re-exported by `generator.py`.
- Produces: `_handle_event(event, text_parts, publish) -> str | None` (returns `stop_reason` when the event carries one, else `None`).
- Produces: `_stream_messages(payload, headers, publish) -> tuple[str, str | None]` (text, stop_reason).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_backend.py`. `_sse_body` currently hardcodes `stop_reason: end_turn`; add a truncated-body helper and a test.

```python
def _sse_body_truncated(text: str) -> bytes:
    """SSE stream that ends with stop_reason=max_tokens (a truncated turn)."""
    events = [
        {"type": "message_start", "message": {"id": "msg", "role": "assistant"}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}},
        {"type": "message_stop"},
    ]
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


async def test_api_generate_truncation_raises_truncated_error(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None, patch_settings: None
) -> None:
    # An unterminated ```html block — exactly what a max_tokens cutoff produces.
    body = "```html\n<!DOCTYPE html><html><body>partial game, cut off mid-"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse_body_truncated(body))

    _patch_client_with(monkeypatch, handler)

    with pytest.raises(_common.GenerationTruncatedError):
        await _api_backend.generate_via_api(
            concept=_CONCEPT,
            style_triplet_summary="x",
            visual_recipe_name="pixel_crt",
        )


async def test_api_generate_model_rejected_is_clear(
    monkeypatch: pytest.MonkeyPatch, patch_recipes: None, patch_settings: None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            content=b'{"error":{"type":"invalid_request_error","message":"model: unknown model"}}',
        )

    _patch_client_with(monkeypatch, handler)

    with pytest.raises(RuntimeError, match="model"):
        await _api_backend.generate_via_api(
            concept=_CONCEPT,
            style_triplet_summary="x",
            visual_recipe_name="pixel_crt",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_backend.py::test_api_generate_truncation_raises_truncated_error tests/test_api_backend.py::test_api_generate_model_rejected_is_clear -v`
Expected: FAIL — `AttributeError: module 'bark_to_game.generate._common' has no attribute 'GenerationTruncatedError'` (first) and the model test fails because the current `>=400` branch raises a message without the word "model" reliably matched / the truncation currently raises the generic "did not contain" error.

- [ ] **Step 3: Add the error class in `_common.py`**

Insert after the `GenerationStalledError` class (currently ends at line 35):

```python
class GenerationTruncatedError(RuntimeError):
    """Raised when the model hit its ``max_tokens`` output cap before finishing
    the game, so the ```html block is incomplete. Distinct from a stall: a
    retry with the same cap would truncate again, so the route layer shows a
    specific message and does NOT retry it."""
```

- [ ] **Step 4: Re-export it from `generator.py`**

Modify the import block (lines 19-23) and `__all__` (lines 26-31):

```python
from bark_to_game.generate._common import (
    GenerationResult,
    GenerationStalledError,
    GenerationTruncatedError,
    RateLimitedError,
)
from bark_to_game.schemas.game import JobEvent

__all__ = [
    "GenerationResult",
    "GenerationStalledError",
    "GenerationTruncatedError",
    "RateLimitedError",
    "generate",
]
```

- [ ] **Step 5: Capture `stop_reason` in `_handle_event`**

In `_api_backend.py`, change the import (lines 31-36) to include the new error:

```python
from bark_to_game.generate._common import (
    GenerationResult,
    GenerationStalledError,
    GenerationTruncatedError,
    RateLimitedError,
    new_game_dir,
)
```

Replace `_handle_event` (lines 439-458) so it returns the stop_reason:

```python
def _handle_event(
    event: dict[str, Any],
    text_parts: list[str],
    publish: Callable[[JobEvent], None] | None,
) -> str | None:
    """Append any text delta; return the terminal ``stop_reason`` if this
    event carried one (``message_delta``), else ``None``."""
    etype = event.get("type")
    if etype == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            text_parts.append(delta.get("text", ""))
    elif etype == "message_delta":
        # Carries the terminal stop_reason: end_turn | max_tokens | ...
        return (event.get("delta") or {}).get("stop_reason")
    elif etype == "message_stop":
        pass
    elif etype == "error":
        err = event.get("error") or {}
        if err.get("type") == "overloaded_error":
            raise RateLimitedError(
                f"API overloaded: {err.get('message', '?')}", resets_at=None
            )
        raise RuntimeError(f"API stream error: {err}")
    return None
```

- [ ] **Step 6: Thread `stop_reason` through `_stream_messages` + clarify model errors**

Change `_stream_messages` return type to `tuple[str, str | None]`. Update the signature line (337-341), add the model-error clarification in the `>= 400` branch (362-366), track `stop_reason` in the loop, and change the return (405).

Signature:
```python
async def _stream_messages(
    payload: dict[str, Any],
    headers: dict[str, str],
    publish: Callable[[JobEvent], None] | None,
) -> tuple[str, str | None]:
```

In the `>= 400` (non-429) branch, replace the `raise RuntimeError(...)` (lines 362-366) with:
```python
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:400]
                    if resp.status_code in (400, 404) and "model" in body.lower():
                        raise RuntimeError(
                            f"API rejected model {settings.API_MODEL!r} "
                            f"(HTTP {resp.status_code}) — check BARK_API_MODEL. {body}"
                        )
                    raise RuntimeError(f"API error HTTP {resp.status_code}: {body}")
```

Add a `stop_reason` local (right after `last_publish_len = 0`, line 351) and capture it in the loop (replace the `_handle_event(...)` call at line 379):
```python
    full_text_parts: list[str] = []
    last_publish_len = 0
    stop_reason: str | None = None
```
```python
                    reason = _handle_event(event, full_text_parts, publish)
                    if reason is not None:
                        stop_reason = reason
```

Change the final return (line 405):
```python
    return "".join(full_text_parts), stop_reason
```

- [ ] **Step 7: Raise on truncation in `generate_via_api`**

Replace the single-line call (line 288) and add the truncation guard before block extraction:

```python
    full_text, stop_reason = await _stream_messages(payload, headers, publish)

    if stop_reason == "max_tokens":
        raise GenerationTruncatedError(
            f"generation hit the {settings.API_MAX_OUTPUT_TOKENS}-token output "
            f"cap before finishing (got {len(full_text)} chars); the html block "
            f"is incomplete"
        )

    blocks = _extract_fenced_blocks(full_text)
```

- [ ] **Step 8: Raise the output cap in `settings.py`**

Replace lines 47-49:
```python
# Hard cap on tokens per generation. Single-file games run 28-33 KB of HTML
# (~10-15k tokens with dense JS); 32000 leaves 2-3x headroom so truncation
# (the dominant husk cause) essentially disappears. Bump via .env if needed.
API_MAX_OUTPUT_TOKENS: int = int(os.getenv("BARK_API_MAX_OUTPUT_TOKENS", "32000"))
```

- [ ] **Step 9: Run the full api-backend test file**

Run: `uv run pytest tests/test_api_backend.py -v`
Expected: PASS — the two new tests pass; all 6 existing tests still pass (the happy-path `_sse_body` emits `stop_reason: end_turn`, so no truncation raise; the tuple return is internal to `generate_via_api`).

- [ ] **Step 10: Type-check**

Run: `uv run mypy bark_to_game/generate/_api_backend.py bark_to_game/generate/_common.py bark_to_game/generate/generator.py bark_to_game/settings.py`
Expected: no errors.

- [ ] **Step 11: Commit**

```bash
git add backend/bark_to_game/generate/_common.py backend/bark_to_game/generate/generator.py backend/bark_to_game/generate/_api_backend.py backend/bark_to_game/settings.py backend/tests/test_api_backend.py
git commit -m "fix(generate): detect max_tokens truncation, raise cap to 32000, clearer model error"
```

---

## Task 2: `_run_job` retry budget + per-attempt husk cleanup

Wrap `generate()` in a bounded retry loop for transient failures (stall / generic RuntimeError), skip retry for rate-limit and truncation, and delete the husk dir left by each failed attempt.

**Files:**
- Modify: `backend/bark_to_game/settings.py` (add `API_MAX_RETRIES`)
- Modify: `backend/bark_to_game/routes/game.py` (imports 15-30; `_friendly_job_error` 81-101; add `_cleanup_husk`; rewrite `_run_job` 132-168)
- Test: `backend/tests/test_game_route.py`

**Interfaces:**
- Consumes: `GenerationTruncatedError` from `bark_to_game.generate.generator`; `settings.API_MAX_RETRIES: int`.
- Produces: `_cleanup_husk(job: JobState) -> None`.
- Behaviour contract: on success job is `done`; on `RateLimitedError`/`GenerationTruncatedError` job is `failed` after exactly 1 `generate()` call; on `GenerationStalledError`/`RuntimeError` `generate()` is called up to `API_MAX_RETRIES + 1` times before the job is `failed`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_game_route.py`:

```python
def test_run_job_retries_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from bark_to_game import settings
    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(settings, "API_MAX_RETRIES", 2)
    calls = {"n": 0}

    async def flaky(**kwargs: Any) -> generator.GenerationResult:
        calls["n"] += 1
        on_start = kwargs.get("on_start")
        game_dir = tmp_path / f"attempt{calls['n']}"
        game_dir.mkdir()
        (game_dir / "CLAUDE.md").write_text("spec")  # husk
        if on_start:
            on_start(str(game_dir))
        if calls["n"] == 1:
            raise generator.GenerationStalledError("stalled once")
        (game_dir / "game.html").write_text("<html></html>")
        return generator.GenerationResult(
            game_id="attempt2", game_path=str(game_dir / "game.html"),
            summary="ok", cwd=str(game_dir),
        )

    monkeypatch.setattr(game_route, "generate", flaky)

    resp = client.post("/api/game/generate", json=_request_body())
    final = _poll(resp.json()["job_id"])
    assert final["status"] == "done"
    assert calls["n"] == 2
    assert not (tmp_path / "attempt1").exists()  # husk from failed attempt cleaned
    assert (tmp_path / "attempt2" / "game.html").exists()  # success kept


def test_run_job_no_retry_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from bark_to_game import settings
    from bark_to_game.routes import game as game_route

    monkeypatch.setattr(settings, "API_MAX_RETRIES", 2)
    calls = {"n": 0}

    async def rate_limited(**_: Any) -> generator.GenerationResult:
        calls["n"] += 1
        raise generator.RateLimitedError("quota", resets_at=None)

    monkeypatch.setattr(game_route, "generate", rate_limited)

    resp = client.post("/api/game/generate", json=_request_body())
    final = _poll(resp.json()["job_id"])
    assert final["status"] == "failed"
    assert calls["n"] == 1  # not retried


def test_run_job_truncated_not_retried_and_husk_cleaned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from bark_to_game import settings
    from bark_to_game.routes import game as game_route
    from bark_to_game.generate.generator import GenerationTruncatedError

    monkeypatch.setattr(settings, "API_MAX_RETRIES", 2)
    calls = {"n": 0}

    async def truncated(**kwargs: Any) -> generator.GenerationResult:
        calls["n"] += 1
        on_start = kwargs.get("on_start")
        game_dir = tmp_path / "husk"
        game_dir.mkdir(exist_ok=True)
        (game_dir / "CLAUDE.md").write_text("spec")
        if on_start:
            on_start(str(game_dir))
        raise GenerationTruncatedError("hit cap")

    monkeypatch.setattr(game_route, "generate", truncated)

    resp = client.post("/api/game/generate", json=_request_body())
    final = _poll(resp.json()["job_id"])
    assert final["status"] == "failed"
    assert calls["n"] == 1  # truncation not retried
    assert "截断" in (final["error"] or "") or "output limit" in (final["error"] or "")
    assert not (tmp_path / "husk").exists()  # husk cleaned
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_game_route.py::test_run_job_retries_transient_then_succeeds tests/test_game_route.py::test_run_job_no_retry_on_rate_limit tests/test_game_route.py::test_run_job_truncated_not_retried_and_husk_cleaned -v`
Expected: FAIL — `AttributeError: settings has no attribute 'API_MAX_RETRIES'` / retry+cleanup behaviour not implemented.

- [ ] **Step 3: Add the retry setting**

Append to `backend/bark_to_game/settings.py`:
```python
# How many times _run_job retries generation on a transient failure (stall /
# unexpected RuntimeError). Rate-limit and truncation are NOT retried. Total
# attempts = API_MAX_RETRIES + 1.
API_MAX_RETRIES: int = int(os.getenv("BARK_API_MAX_RETRIES", "2"))
```

- [ ] **Step 4: Add imports + `_cleanup_husk` in `routes/game.py`**

Add to the top-of-file imports:
```python
import shutil
from pathlib import Path
```
Add `GenerationTruncatedError` to the generator import (lines 16-20):
```python
from bark_to_game.generate.generator import (
    GenerationStalledError,
    GenerationTruncatedError,
    RateLimitedError,
    generate,
)
```
Add `from bark_to_game import settings`:
```python
from bark_to_game import settings
```
Add the helper (place it just above `_run_job`):
```python
def _cleanup_husk(job: JobState) -> None:
    """Delete the per-game dir left by a FAILED attempt (a 'husk': CLAUDE.md
    but no game.html). Never touches a dir that has game.html. Resets the
    job's cwd pointer so a subsequent retry records its own dir."""
    cwd = job.subprocess_cwd
    if not cwd:
        return
    husk = Path(cwd)
    try:
        if husk.is_dir() and not (husk / "game.html").exists():
            shutil.rmtree(husk, ignore_errors=True)
            logger.info(f"job {job.job_id}: removed husk dir {husk.name}")
    except OSError as exc:
        logger.warning(f"job {job.job_id}: husk cleanup failed - {exc!r}")
    finally:
        job.subprocess_cwd = None
```

- [ ] **Step 5: Add the "truncated" friendly message**

In `_friendly_job_error` (lines 81-101), add before the `detail = ...` fallback:
```python
    if kind == "truncated":
        return (
            "游戏内容太大,生成中途被截断了,请重试。 "
            "(Generation hit the output limit — please retry.)"
        )
```

- [ ] **Step 6: Rewrite `_run_job` with the retry loop**

Replace `_run_job` (lines 132-168) entirely:
```python
async def _run_job(job: JobState, req: GenerateRequest) -> None:
    job.mark_running()
    logger.info(f"job {job.job_id}: running (recipe={req.visual_recipe})")
    max_attempts = settings.API_MAX_RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            result = await generate(
                concept=req.concept.model_dump(),
                style_triplet_summary=_style_summary(req),
                visual_recipe_name=req.visual_recipe,
                game_params=req.game_params.model_dump(),
                on_start=lambda cwd: _remember_cwd(job, cwd),
                publish=job.publish,
            )
        except asyncio.CancelledError:
            job.mark_cancelled()
            job.publish(_terminal_event(job))
            logger.info(f"job {job.job_id}: cancelled ({job.elapsed_s():.0f}s)")
            raise
        except RateLimitedError as exc:
            job.mark_failed(_friendly_job_error("rate_limited", exc))
            job.publish(_terminal_event(job))
            _reap_post_failure(job, "rate-limited")
            _cleanup_husk(job)
            logger.warning(f"job {job.job_id}: rate-limited (resets_at={exc.resets_at})")
            return
        except GenerationTruncatedError as exc:
            job.mark_failed(_friendly_job_error("truncated", exc))
            job.publish(_terminal_event(job))
            _reap_post_failure(job, "truncated")
            _cleanup_husk(job)
            logger.warning(f"job {job.job_id}: truncated - {exc!r}")
            return
        except (GenerationStalledError, RuntimeError) as exc:
            _reap_post_failure(job, "retryable")
            _cleanup_husk(job)
            if attempt < max_attempts:
                logger.warning(
                    f"job {job.job_id}: attempt {attempt}/{max_attempts} failed "
                    f"({type(exc).__name__}: {exc}); retrying"
                )
                continue
            kind = "stalled" if isinstance(exc, GenerationStalledError) else "errored"
            job.mark_failed(_friendly_job_error(kind, exc))
            job.publish(_terminal_event(job))
            logger.warning(f"job {job.job_id}: failed after {attempt} attempts - {exc!r}")
            return
        else:
            job.mark_done(game_id=result["game_id"], summary=result["summary"])
            _record_history(job, req, result["game_id"])
            job.publish(_terminal_event(job))
            logger.info(
                f"job {job.job_id}: done game_id={result['game_id']} ({job.elapsed_s():.0f}s)"
            )
            return
```

Note ordering: `RateLimitedError` and `GenerationTruncatedError` are both `RuntimeError` subclasses, so their `except` clauses MUST precede the generic `(GenerationStalledError, RuntimeError)` clause. `GenerationStalledError` is also a `RuntimeError` subclass and is caught by the tuple.

- [ ] **Step 7: Run the game-route tests**

Run: `uv run pytest tests/test_game_route.py -v`
Expected: PASS — the 3 new tests plus all existing route tests (`test_generate_job_records_failure` still passes: `boom` raises `RuntimeError`, now retried `API_MAX_RETRIES` times — but the default `API_MAX_RETRIES=2` means 3 calls, still ends `failed` with the message; the assertion only checks final status + error substring, which still holds).

> If `test_generate_job_records_failure` becomes slow or flaky from retries, set `monkeypatch.setattr(settings, "API_MAX_RETRIES", 0)` at its top so it stays a single-attempt failure test. Include that one-line change in this step if needed.

- [ ] **Step 8: Type-check**

Run: `uv run mypy bark_to_game/routes/game.py bark_to_game/settings.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/bark_to_game/routes/game.py backend/bark_to_game/settings.py backend/tests/test_game_route.py
git commit -m "fix(generate): retry transient job failures, clean husk dirs, skip retry on rate-limit/truncation"
```

---

## Task 3: One-time husk sweep utility

A standalone module to delete pre-existing husk dirs (the ~16 already on disk). Runtime cleanup (Task 2) prevents new ones; this cleans the backlog.

**Files:**
- Create: `backend/bark_to_game/generate/maintenance.py`
- Test: `backend/tests/test_maintenance.py`

**Interfaces:**
- Produces: `sweep_husks(games_dir: Path | None = None, *, dry_run: bool = False) -> list[str]` — returns the names of husk dirs (removed unless `dry_run`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_maintenance.py`:
```python
"""Tests for the husk-sweep maintenance utility."""

from __future__ import annotations

from pathlib import Path

from bark_to_game.generate.maintenance import sweep_husks


def test_sweep_removes_husks_keeps_games(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.mkdir()
    (good / "game.html").write_text("<html></html>")
    (good / "CLAUDE.md").write_text("spec")

    husk1 = tmp_path / "husk1"
    husk1.mkdir()
    (husk1 / "CLAUDE.md").write_text("spec")  # no game.html
    husk2 = tmp_path / "husk2"
    husk2.mkdir()  # empty

    (tmp_path / "loose.txt").write_text("not a dir entry we touch")

    removed = sweep_husks(tmp_path, dry_run=False)

    assert set(removed) == {"husk1", "husk2"}
    assert good.exists() and (good / "game.html").exists()
    assert not husk1.exists()
    assert not husk2.exists()


def test_sweep_dry_run_reports_but_keeps(tmp_path: Path) -> None:
    husk = tmp_path / "husk"
    husk.mkdir()
    (husk / "CLAUDE.md").write_text("spec")

    removed = sweep_husks(tmp_path, dry_run=True)

    assert removed == ["husk"]
    assert husk.exists()  # dry-run did not delete
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_maintenance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bark_to_game.generate.maintenance'`.

- [ ] **Step 3: Implement the module**

Create `backend/bark_to_game/generate/maintenance.py`:
```python
"""One-off maintenance: remove husk game dirs (a dir with no game.html).

Husks are left by generations that failed before writing game.html. Task 2's
runtime cleanup prevents new husks; this sweeps the pre-existing backlog.

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_maintenance.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Type-check**

Run: `uv run mypy bark_to_game/generate/maintenance.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/bark_to_game/generate/maintenance.py backend/tests/test_maintenance.py
git commit -m "feat(generate): add husk-sweep maintenance utility"
```

- [ ] **Step 7: Run the sweep (ops — dry-run first, then apply) — local + server**

Local:
```bash
cd backend && uv run python -m bark_to_game.generate.maintenance          # review list
cd backend && uv run python -m bark_to_game.generate.maintenance --apply  # delete
```
Server (over SSH, `/opt/bark-to-game/backend`): same two commands via the deployed venv. This is a manual ops step, not part of the PR — record the deleted count in the PR description.

---

## Final verification

- [ ] **Run the whole backend suite**

Run: `uv run pytest -q`
Expected: all tests pass (existing + new). Note the new total in the PR body.

- [ ] **Type-check the package**

Run: `uv run mypy bark_to_game`
Expected: no errors.

- [ ] **Open PR to `dev`**

Push `feat/stability-sharing` and open a PR against `dev` titled `fix(generate): generation reliability (truncation, retry, husk cleanup)`. Body: what changed, the husk-sweep counts (local + server), new test count.

---

## Self-Review

**1. Spec coverage** (against spec §设计 D):
- 截断检测 + 续写/提高 cap → Task 1 (detect `max_tokens`, cap→32000). Continuation deliberately dropped in favour of the cap bump — documented in the plan intro and spec (both were spec-listed options); avoids speculative assistant-prefill API code. ✓
- 生成重试预算(不对 RateLimited 重试) → Task 2. ✓
- 空壳清理(运行时 + 一次性清扫已有 16 个) → Task 2 (per-attempt) + Task 3 (backlog sweep). ✓
- 模型 id 自检 → Task 1 Step 6 (clear error when the proxy rejects the model id — the practical form of a "sanity check"; a startup API probe was rejected as too costly/latency-heavy for low value since production proves the ids resolve). ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every run step shows the command + expected result. ✓

**3. Type consistency:** `GenerationTruncatedError` defined in `_common.py`, re-exported in `generator.py` `__all__`, imported in both `_api_backend.py` and `routes/game.py`. `_stream_messages -> tuple[str, str | None]` matches its single caller in `generate_via_api` (`full_text, stop_reason = await ...`). `_handle_event -> str | None` matches its use (`reason = _handle_event(...)`). `_cleanup_husk(job)` / `sweep_husks(games_dir, *, dry_run)` names consistent across tasks and tests. `settings.API_MAX_RETRIES` / `settings.API_MAX_OUTPUT_TOKENS` consistent. ✓
