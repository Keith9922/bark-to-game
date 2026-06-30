"""Style-card loading + seeded triplet selection."""

from __future__ import annotations

from bark_to_game.translate import style_cards


def test_pools_have_min_entries() -> None:
    assert len(style_cards._load_art()) >= 8
    assert len(style_cards._load_mechanics()) >= 8
    assert len(style_cards._load_moods()) >= 8


def test_every_mechanic_carries_core_loop() -> None:
    """Translate prompt references mechanic.core_loop — guard against missing keys."""
    for m in style_cards._load_mechanics():
        assert m["core_loop"], f"mechanic {m['name']} missing core_loop"
        assert len(m["core_loop"]) > 20, f"mechanic {m['name']} core_loop too short"


def test_pick_is_deterministic_for_seed() -> None:
    a = style_cards.pick_triplet(seed=42)
    b = style_cards.pick_triplet(seed=42)
    assert a == b


def test_pick_varies_with_different_seeds() -> None:
    seeds = list(range(20))
    triplets = [style_cards.pick_triplet(seed=s) for s in seeds]
    art_names = {t["art"]["name"] for t in triplets}
    # Over 20 seeds we expect to see at least 3 distinct art styles
    assert len(art_names) >= 3


def test_pick_with_no_occupied_cells_is_uniform() -> None:
    """Empty/None occupied cells must behave identically to the legacy unweighted pick."""
    a = style_cards.pick_triplet(seed=7, occupied_cells=set())
    b = style_cards.pick_triplet(seed=7, occupied_cells=None)
    c = style_cards.pick_triplet(seed=7)
    assert a == b == c


def test_pick_avoids_recently_used_cards_under_archive_pressure() -> None:
    """When most cards are 'used', unused ones should dominate the next picks."""
    art_pool = [a["name"] for a in style_cards._load_art()]
    # Mark all but one art name as used in prior cells (mood/mechanic free).
    # The single unused art name should appear far more often than chance.
    spared = art_pool[0]
    occupied = {(name, "catch", "serene") for name in art_pool[1:]}

    spared_hits = 0
    trials = 200
    for s in range(trials):
        t = style_cards.pick_triplet(seed=s, occupied_cells=occupied)
        if t["art"]["name"] == spared:
            spared_hits += 1

    # Under uniform weighting the spared name would land ~ trials / N_arts.
    # Our soft penalty (0.5 per overlap) makes it ~2x more likely.
    uniform_expectation = trials / len(art_pool)
    assert spared_hits > uniform_expectation * 1.4, (
        f"archive pressure failed: spared={spared_hits}, uniform={uniform_expectation:.1f}"
    )
