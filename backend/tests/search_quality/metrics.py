"""IR metrics for search ranking evaluation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def hit_at_k(ranked_codes: Sequence[str], relevant: Mapping[str, int], *, k: int = 5) -> float:
    top = ranked_codes[:k]
    return 1.0 if any(relevant.get(code, 0) > 0 for code in top) else 0.0


def mrr(
    ranked_codes: Sequence[str],
    relevant: Mapping[str, int],
    *,
    preferred: str | None = None,
) -> float:
    targets = {preferred} if preferred else {c for c, rel in relevant.items() if rel > 0}
    if not targets or targets == {None}:
        targets = {c for c, rel in relevant.items() if rel > 0}
    for idx, code in enumerate(ranked_codes, start=1):
        if code in targets:
            return 1.0 / idx
    return 0.0


def _dcg(relevances: Sequence[float]) -> float:
    total = 0.0
    for i, rel in enumerate(relevances, start=1):
        total += (2**rel - 1) / math.log2(i + 1)
    return total


def ndcg_at_k(ranked_codes: Sequence[str], relevant: Mapping[str, int], *, k: int = 5) -> float:
    gains = [float(relevant.get(code, 0)) for code in ranked_codes[:k]]
    ideal = sorted((float(v) for v in relevant.values() if v > 0), reverse=True)[:k]
    if not ideal:
        return 0.0
    ideal_dcg = _dcg(ideal)
    if ideal_dcg <= 0:
        return 0.0
    return _dcg(gains) / ideal_dcg


def exact_top1(ranked_codes: Sequence[str], expected_top: str | None) -> float | None:
    if not expected_top:
        return None
    if not ranked_codes:
        return 0.0
    return 1.0 if ranked_codes[0] == expected_top else 0.0


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
