"""Pinned numerical resolution for objective comparison.

The three objectives are floating-point results of a discrete simulation, so
two decisions that are physically identical can differ in the last few bits.
Treating those bits as real trade-offs produces artefacts: a Pareto front that
claims a fairness gain from a 2e-13 difference in `F3` while ignoring an 11%
difference in `F1`, and a representative choice that follows the noise.

This module defines one place where the resolution of each objective is fixed,
and a deterministic quantization key built from it. Comparisons that must agree
with each other -- dominance, archive membership, de-duplication, rank and
crowding, representative selection and the quality indicators -- all go through
the same key, so they cannot disagree.

The resolution is a *service* resolution, not an arithmetic one: it is the
smallest difference in an objective that the study is willing to call a
difference at all. It is fixed here, in advance, and never chosen from the
outcome of a run.

See docs/model_v2_contract.md for the rationale behind the magnitudes.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Sequence


# F1 is a sum over periods of an unmet fraction, so it accumulates the same
# rounding as a single satisfaction ratio (~1e-12 over a 9-period horizon), and
# F3 is one such ratio. 1e-8 is four orders of magnitude above that arithmetic
# noise while still far below any service change worth reporting: on the
# Wenchuan case it corresponds to about 1e-4 tons of demand.
FRACTION_RESOLUTION = 1e-8

# F2 is a sum of travel minutes over trips. Its arithmetic noise is smaller
# still, but the objective is reported on a minutes scale, so 1e-6 minutes
# (60 microseconds) is the smallest difference worth distinguishing.
MINUTES_RESOLUTION = 1e-6


@dataclass(frozen=True)
class ObjectivePrecision:
    """Per-objective resolution and the comparison key derived from it.

    A resolution of exactly 0.0 means "compare raw values", which is the
    historical legacy rule and is kept for regression.
    """

    label: str
    resolutions: tuple[float, float, float]

    @property
    def is_exact(self) -> bool:
        return all(resolution == 0.0 for resolution in self.resolutions)

    def key(self, objectives: Sequence[float]) -> tuple[Any, Any, Any]:
        """Deterministic comparison key.

        Quantizing to integers gives a total preorder that is transitive and
        antisymmetric, unlike a chain of `isclose` tests, which is not a valid
        order and must not be used for sorting, fronts or dominance.
        """
        if self.is_exact:
            return (float(objectives[0]), float(objectives[1]), float(objectives[2]))
        return tuple(
            int(round(float(value) / resolution))
            for value, resolution in zip(objectives, self.resolutions)
        )

    def dominates(self, left: Sequence[float], right: Sequence[float]) -> bool:
        """Dominance on the quantized key.

        Dominance over integer vectors is a strict partial order: irreflexive,
        antisymmetric and transitive. Quantizing first is what makes a 2e-13
        difference neither a trade-off nor a win.
        """
        left_key = self.key(left)
        right_key = self.key(right)
        return all(a <= b for a, b in zip(left_key, right_key)) and any(
            a < b for a, b in zip(left_key, right_key)
        )

    def equivalent(self, left: Sequence[float], right: Sequence[float]) -> bool:
        return self.key(left) == self.key(right)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "resolutions": list(self.resolutions),
            "exact": self.is_exact,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# Historical rule: raw comparison, no resolution. Kept for legacy regression.
EXACT_PRECISION = ObjectivePrecision("legacy_exact", (0.0, 0.0, 0.0))

# Frozen v2 rule. The order is (F1, F2, F3).
V2_PRECISION = ObjectivePrecision(
    "v2_service_resolution",
    (FRACTION_RESOLUTION, MINUTES_RESOLUTION, FRACTION_RESOLUTION),
)


def precision_for(instance: Any) -> ObjectivePrecision:
    """Precision implied by an instance's evaluation profile."""
    version = getattr(getattr(instance, "evaluation", None), "model_version", "legacy")
    return V2_PRECISION if version == "v2" else EXACT_PRECISION


def key_front(points: Sequence[Sequence[float]], precision: ObjectivePrecision) -> list[tuple]:
    """Non-dominated comparison keys over `points`, de-duplicated.

    Two points with the same key are one point: the survivor is chosen by the
    lowest raw tuple so the result does not depend on input order. This is the
    single place that decides which comparison keys a front is made of, so the
    reference front, the distance coordinates and the reported front cannot
    disagree about it.
    """
    by_key: dict[tuple, Sequence[float]] = {}
    for point in sorted(points):
        by_key.setdefault(precision.key(point), point)
    keys = list(by_key)
    non_dominated = [
        key
        for key in keys
        if not any(precision.dominates(other, key) for other in keys if other != key)
    ]
    return sorted(non_dominated)


def narrow_coordinates(
    keys: Sequence[Sequence[float]],
    ideal_key: Sequence[float],
    nadir_key: Sequence[float],
) -> list[tuple[float, float, float]]:
    """Map comparison keys into [0, 1] per dimension.

    Distances are measured in the comparison coordinates, not in raw values, so
    a dimension that is constant at the resolution maps to one constant and
    contributes nothing. Its raw tail is never integrated.
    """
    spans = [nadir_key[idx] - ideal_key[idx] for idx in range(3)]
    return [
        tuple(
            (key[idx] - ideal_key[idx]) / spans[idx] if spans[idx] > 0 else 0.0
            for idx in range(3)
        )
        for key in keys
    ]


def key_bounds(
    keys: Sequence[Sequence[float]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    ideal = tuple(min(key[idx] for key in keys) for idx in range(3))
    nadir = tuple(max(key[idx] for key in keys) for idx in range(3))
    return ideal, nadir


def effective_span(
    ideal: float,
    nadir: float,
    resolution: float,
) -> tuple[float, bool]:
    """Range to normalize by, and whether it had to be floored.

    A dimension whose observed range is smaller than the resolution carries no
    usable information; flooring it keeps min-max normalization from turning
    rounding noise into the dominant source of spread.
    """
    observed = nadir - ideal
    if resolution <= 0.0:
        return observed, False
    if observed <= resolution:
        return resolution, True
    return observed, False


def degenerate_dimensions(
    ideal: Sequence[float],
    nadir: Sequence[float],
    precision: ObjectivePrecision,
) -> list[int]:
    """Indices whose observed range is below the resolution."""
    return [
        index
        for index, resolution in enumerate(precision.resolutions)
        if resolution > 0.0 and (nadir[index] - ideal[index]) <= resolution
    ]


def safe_ratio(numerator: float, denominator: float) -> float | None:
    """Percentage helper that reports a zero denominator as missing."""
    if denominator == 0.0 or not math.isfinite(denominator):
        return None
    return numerator / denominator
