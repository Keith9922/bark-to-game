"""Style-card loading + seeded triplet selection."""

from __future__ import annotations

from bark_to_game.translate import style_cards


def test_pools_have_min_entries() -> None:
    assert len(style_cards._load_art()) >= 8
    assert len(style_cards._load_mechanics()) >= 8
    assert len(style_cards._load_moods()) >= 8


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
