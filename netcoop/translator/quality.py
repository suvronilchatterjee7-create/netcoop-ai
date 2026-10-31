"""Data-quality scoring (documented in docs/SCORING.md, section 'Data quality').

score = prod(c_i ** w_i) ** (1 / sum(w_i)) over completeness, freshness, plausibility and
mapping certainty: a weighted geometric mean, so one bad dimension cannot be hidden by
good ones. Weights come from config/translator.yaml.
"""

from __future__ import annotations

import math

from netcoop.config import get_value, load_config
from netcoop.protocol.common import DataQuality


def combine(
    completeness: float,
    freshness: float,
    plausibility: float,
    mapping_certainty: float,
    issues: tuple[str, ...] = (),
) -> DataQuality:
    weights: dict[str, float] = get_value(load_config("translator"), "quality.weights")
    parts = {
        "completeness": completeness,
        "freshness": freshness,
        "plausibility": plausibility,
        "mapping_certainty": mapping_certainty,
    }
    total = sum(weights.values())
    if any(v <= 0 for k, v in parts.items() if weights[k] > 0):
        score = 0.0
    else:
        score = math.exp(sum(weights[k] * math.log(v) for k, v in parts.items()) / total)
    clip = {k: min(1.0, max(0.0, v)) for k, v in parts.items()}
    return DataQuality(score=min(1.0, max(0.0, score)), issues=tuple(sorted(set(issues))), **clip)


def freshness(age_s: float, interval_s: float) -> float:
    """1 while age <= stale_after; then halves every half-life."""
    cfg = load_config("translator")
    stale_after = get_value(cfg, "time.stale_after_intervals") * interval_s
    half_life = get_value(cfg, "time.freshness_half_life_intervals") * interval_s
    if age_s <= stale_after or half_life <= 0:
        return 1.0
    return float(0.5 ** ((age_s - stale_after) / half_life))
