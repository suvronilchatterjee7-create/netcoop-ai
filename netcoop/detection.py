"""Shared anomaly-detection library (docs/SCORING.md section 2).

Methods, all deterministic and distribution-free where possible:

* **Percentile band** from calibrated normal operation per (metric, device type): a sample
  is abnormal beyond the ``band_quantile`` (worse side only).
* **Robust z** of the recent median against the calibrated median, with spread
  ``max(1.4826 * MAD, (band - median) / z_at_band)`` so normally-constant counters still have
  a finite scale.
* **Persistence:** significant only if at least ``min_persistence`` of the recent samples are
  abnormal (spikes are ignored).
* **Cited thresholds** (config/detection.yaml ``thresholds``) give a second, absolute test.
* **In-window change:** recent median vs the series' own earlier samples (adapts to the
  current noise level; catches faults that began inside the window).
* **Trend:** Mann-Kendall test with Theil-Sen slope for counters where *rising* matters.

Assumptions: samples of normal operation are exchangeable across devices of one type (the
band is pooled per type); recent samples reflect the current state; Mann-Kendall assumes no
strong serial correlation (mild AR noise inflates its false-positive rate somewhat, hence the
strict alpha).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any

from netcoop.config import ConfigError, get_value, load_config
from netcoop.protocol.common import ComparisonBasis, Direction, Statistic
from netcoop.protocol.payloads import ObservationPayload
from netcoop.protocol.vocabulary import get_vocabulary

MAD_TO_SIGMA = 1.4826  # consistency constant: sigma = 1.4826 * MAD for normal data
MEDIAN_SE = 1.2533  # sqrt(pi/2): asymptotic SE of the median = 1.2533 * sigma / sqrt(n)
AR_MAX = 0.9  # cap on estimated autocorrelation so the inflation factor stays finite (sqrt(19) max)


@dataclass(frozen=True)
class Baseline:
    median: float
    mad: float
    p_low: float
    p_high: float
    n: int
    key: str  # config key it came from


@dataclass(frozen=True)
class Finding:
    """Outcome of evaluating one series; becomes a CLUE payload."""

    statistic: Statistic
    value: float
    unit: str
    direction: Direction
    deviation: float
    deviation_unit: str
    significant: bool
    persistence: float | None
    basis: ComparisonBasis
    reference: float | None
    spread: float | None
    config_key: str
    method: str


class Detector:
    def __init__(self) -> None:
        cfg = load_config("detection")
        self.recent_fraction = float(get_value(cfg, "window.recent_fraction"))
        self.min_samples = int(get_value(cfg, "window.min_samples"))
        self.min_persistence = float(get_value(cfg, "significance.min_persistence"))
        self.z_at_band = float(get_value(cfg, "significance.z_at_band"))
        self.max_dev = float(get_value(cfg, "significance.max_deviation"))
        self.change_z = float(get_value(cfg, "change.min_z"))
        self.thr_se = float(get_value(cfg, "threshold_test.min_standard_errors"))
        self.trend_metrics = set(get_value(cfg, "trend.metrics"))
        self.trend_alpha = float(get_value(cfg, "trend.alpha"))
        self.trend_min = int(get_value(cfg, "trend.min_samples"))
        self.healthy = {k: set(v["value"]) for k, v in cfg["enum_health"].items()}
        self.thresholds = {k: float(v["value"]) for k, v in cfg["thresholds"].items()}
        self.vocab = get_vocabulary()
        try:
            self.baselines: dict[str, Any] = load_config("baselines").get("baselines", {})
        except ConfigError:
            self.baselines = {}

    # ------------------------------------------------------------------ baselines
    def baseline(self, metric: str, entity_type: str) -> Baseline | None:
        per_metric = self.baselines.get(metric, {})
        category = self.vocab.category_of(entity_type)
        for key in (entity_type, f"category:{category}"):
            entry = per_metric.get(key)
            if entry is not None:
                v = entry["value"]
                return Baseline(
                    v["median"],
                    v["mad"],
                    v["p_low"],
                    v["p_high"],
                    v["n"],
                    f"baselines.{metric}.{key}",
                )
        return None

    def recent(self, values: list[Any]) -> list[Any]:
        n = max(self.min_samples, math.ceil(self.recent_fraction * len(values)))
        return values[-n:]

    # ------------------------------------------------------------------ levels
    def evaluate(self, obs: ObservationPayload) -> Finding | None:
        """Level evidence for one numeric/enum series, or None if it cannot be judged.

        Three independent tests, reported in this order of preference when significant:
        calibrated band, cited threshold, in-window change. When none is significant the
        calibrated (else threshold, else change) comparison is reported as negative evidence.
        """
        mdef = self.vocab.metrics[obs.metric]
        values = [p.v for p in obs.points]
        if len(values) < self.min_samples:
            return None
        if mdef.kind == "enum":
            return self._evaluate_enum(obs, values)
        if mdef.worse_when not in ("higher", "lower"):
            return None
        sign = 1.0 if mdef.worse_when == "higher" else -1.0
        nums = [float(v) for v in values]
        recent = self.recent(nums)
        level = median(recent)
        unit = mdef.unit
        candidates: list[Finding] = []

        def worse_frac(limit: float) -> float:
            return sum(1 for x in recent if sign * (x - limit) > 0) / len(recent)

        def direction(ref: float) -> Direction:
            return Direction.ABOVE if level >= ref else Direction.BELOW

        base = self.baseline(obs.metric, obs.entity.entity_type)
        base_spread: float | None = None
        if base is not None:
            band = base.p_high if sign > 0 else base.p_low
            base_spread = max(
                MAD_TO_SIGMA * base.mad, abs(band - base.median) / self.z_at_band, 1e-12
            )
            dev = min(self.max_dev, max(0.0, sign * (level - base.median) / base_spread))
            pers = worse_frac(band)
            candidates.append(
                Finding(
                    Statistic.MEDIAN,
                    level,
                    unit,
                    direction(base.median),
                    dev,
                    "robust_z",
                    pers >= self.min_persistence,
                    pers,
                    ComparisonBasis.BASELINE,
                    base.median,
                    base_spread,
                    base.key,
                    "calibrated_percentile_band",
                )
            )
        thr = self.thresholds.get(obs.metric)
        if thr is not None:
            pers = worse_frac(thr)
            dev = max(0.0, sign * (level - thr)) / max(abs(thr), 1e-12)
            r_mad = median(abs(x - level) for x in recent)
            se = MEDIAN_SE * MAD_TO_SIGMA * r_mad / math.sqrt(len(recent))
            clears = sign * (level - thr) > self.thr_se * se
            candidates.append(
                Finding(
                    Statistic.MEDIAN,
                    level,
                    unit,
                    direction(thr),
                    dev,
                    "relative_to_threshold",
                    pers >= self.min_persistence and clears,
                    pers,
                    ComparisonBasis.THRESHOLD,
                    thr,
                    None,
                    f"detection.thresholds.{obs.metric}",
                    "cited_threshold",
                )
            )
        early = nums[: len(nums) - len(recent)]
        if len(early) >= self.min_samples:
            # Two-sample test on medians: shift / sqrt(SE_recent^2 + SE_early^2), each SE from
            # that segment's own MAD, so the test adapts to the current noise level.
            e_med = median(early)
            se_e = _median_se(early, e_med)
            se_r = _median_se(recent, level)
            se = math.hypot(se_e, se_r)
            if se <= 0:  # constant segments (e.g. idle counters): fall back to the calibrated scale
                se = base_spread or 1e-12
            dev = min(self.max_dev, max(0.0, sign * (level - e_med) / se))
            pers = worse_frac(max(early) if sign > 0 else min(early))
            candidates.append(
                Finding(
                    Statistic.MEDIAN,
                    level,
                    unit,
                    direction(e_med),
                    dev,
                    "median_shift_z",
                    dev >= self.change_z and pers >= self.min_persistence,
                    pers,
                    ComparisonBasis.BASELINE,
                    e_med,
                    se,
                    "detection.change.min_z",
                    "in_window_change",
                )
            )
        if not candidates:
            return None
        # A test only counts if the recent median itself is on the worse side (deviation > 0);
        # persistence alone can reach 50% by chance when half the samples straddle a limit.
        significant = [c for c in candidates if c.significant and c.deviation > 0]
        if significant:
            return significant[0]
        first = candidates[0]
        return Finding(**{**first.__dict__, "significant": False})

    def _evaluate_enum(self, obs: ObservationPayload, values: list[Any]) -> Finding | None:
        healthy = self.healthy.get(obs.metric)
        if healthy is None:
            return None
        recent = self.recent(values)
        bad = sum(1 for v in recent if v not in healthy) / len(recent)
        base = self.baseline(obs.metric, obs.entity.entity_type)
        normal_bad = base.p_high if base else 0.0
        significant = bad >= self.min_persistence and bad > normal_bad
        return Finding(
            Statistic.FRACTION,
            bad,
            "ratio",
            Direction.CHANGED if bad > normal_bad else Direction.BELOW,
            bad,
            "fraction_abnormal",
            significant,
            bad,
            ComparisonBasis.BASELINE if base else ComparisonBasis.THRESHOLD,
            normal_bad,
            None,
            base.key if base else "detection.enum_health." + obs.metric,
            "abnormal_state_fraction",
        )

    # ------------------------------------------------------------------ trends
    def trend(self, obs: ObservationPayload) -> Finding | None:
        if obs.metric not in self.trend_metrics:
            return None
        # 'rising' means still rising now: the trend is tested on the recent window, so a step
        # that has levelled off (e.g. a failed device's flat error level) is not a trend
        ys = self.recent([float(p.v) for p in obs.points])
        if len(ys) < self.trend_min:
            return None
        z, p = mann_kendall(ys)
        slope = theil_sen(ys)
        rising = slope > 0 and z > 0
        return Finding(
            Statistic.SLOPE,
            slope,
            f"{obs.unit}/interval",
            Direction.ABOVE if slope >= 0 else Direction.BELOW,
            min(self.max_dev, abs(z)),
            "mann_kendall_z",
            rising and p < self.trend_alpha,
            None,
            ComparisonBasis.THRESHOLD,
            0.0,
            None,
            "detection.trend.alpha",
            "mann_kendall+theil_sen",
        )


def lag1_autocorrelation(xs: list[float]) -> float:
    """Lag-1 autocorrelation, clipped to [0, AR_MAX] (negative values do not shrink the SE)."""
    n = len(xs)
    mu = sum(xs) / n
    den = sum((x - mu) ** 2 for x in xs)
    if den <= 0:
        return 0.0
    rho = sum((xs[i] - mu) * (xs[i + 1] - mu) for i in range(n - 1)) / den
    return min(AR_MAX, max(0.0, rho))


def _median_se(xs: list[float], med: float) -> float:
    """SE of a segment's median, inflated for AR(1) dependence: sqrt((1+rho)/(1-rho))."""
    sigma = MAD_TO_SIGMA * median(abs(x - med) for x in xs)
    rho = lag1_autocorrelation(xs)
    return MEDIAN_SE * sigma / math.sqrt(len(xs)) * math.sqrt((1 + rho) / (1 - rho))


def mann_kendall(ys: list[float]) -> tuple[float, float]:
    """Mann-Kendall trend test: (z, two-sided p) with tie correction."""
    n = len(ys)
    s = sum((ys[j] > ys[i]) - (ys[j] < ys[i]) for i in range(n - 1) for j in range(i + 1, n))
    ties: dict[float, int] = {}
    for y in ys:
        ties[y] = ties.get(y, 0) + 1
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties.values())) / 18
    if var <= 0:
        return 0.0, 1.0
    z = (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var) if s < 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    return z, p


def theil_sen(ys: list[float]) -> float:
    """Median of pairwise slopes (per sample interval)."""
    slopes = [(ys[j] - ys[i]) / (j - i) for i in range(len(ys) - 1) for j in range(i + 1, len(ys))]
    return float(median(slopes)) if slopes else 0.0


def quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation quantile of an already sorted list."""
    if not sorted_values:
        raise ValueError("empty")
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)
