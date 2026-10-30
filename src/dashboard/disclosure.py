"""Disclosure control shared by the offline dashboard builders.

Primary suppression hides cells with fewer than MIN_CELL_SAMPLE sample households. Secondary suppression then closes
the gaps that subtraction would open: when a published total equals the sum of published parts (district = urban +
rural, Rwanda = sum of districts, all households = female head + male head, ...), a single hidden cell could be
recovered as total minus the others, so a second cell is hidden. A minimum sample size alone does not prove a release
is safe; these rules are documented in docs/community_planning_app_spec.md and still need NISR review.
"""
from __future__ import annotations

from collections.abc import Hashable, Iterable

import pandas as pd

MIN_CELL_SAMPLE = 30


def secondary_suppression(suppressed: pd.Series, sample: pd.Series,
                          relations: Iterable[tuple[Hashable, list[Hashable]]]) -> pd.Series:
    """Extend `suppressed` (indexed like `sample`) so no additive relation has exactly one hidden member.

    Each relation is (total_index, [part_indices]) with total = sum of parts. If exactly one member is hidden, the
    published part with the smallest sample is hidden too. Repeats until stable, since relations share cells.
    """
    sup = suppressed.astype(bool).copy()
    relations = [(t, list(p)) for t, p in relations]
    changed = True
    while changed:
        changed = False
        for total, parts in relations:
            members = [total, *parts]
            hidden = sum(bool(sup[m]) for m in members)
            open_parts = [p for p in parts if not sup[p]]
            if hidden == 1 and open_parts:
                sup[min(open_parts, key=lambda p: sample[p])] = True
                changed = True
    return sup


def nested_level_suppression(sample_by_level: dict[float, int], population_sample: int) -> set[float]:
    """Levels to hide for nested selections (top 10% within top 20% within top 30% within everyone).

    Publishing two nested selections lets anyone difference them, so every slice between consecutive published levels,
    and between the largest published level and the whole population, must hold at least MIN_CELL_SAMPLE households.
    """
    hidden: set[float] = set()
    while True:
        levels = sorted(v for v in sample_by_level if v not in hidden)
        prev = 0
        bad = None
        for lv in levels:
            if sample_by_level[lv] - prev < MIN_CELL_SAMPLE:
                bad = lv
                break
            prev = sample_by_level[lv]
        if bad is None and levels and 0 < population_sample - prev < MIN_CELL_SAMPLE:
            bad = levels[-1]
        if bad is None:
            return hidden
        hidden.add(bad)
