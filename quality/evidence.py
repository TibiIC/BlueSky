"""Evidence levels and the error-mechanism library.

A correction is principled when it is the simplest known error mechanism that makes the record
agree with the strongest available independent evidence, and its confidence reflects how much
better it fits than the alternatives, including "nothing is wrong".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Strongest first. The base confidence is what a clean, unambiguous fit at that level earns.
LEVELS: dict[str, tuple[str, float]] = {
    'A': ('Authoritative source', 0.98),          # an external register that legally wins
    'B': ('Independent second record', 0.95),     # the same fact recorded elsewhere
    'C': ('Physical or accounting constraint', 0.9),
    'D': ('History of the same item', 0.8),       # same meter / system / supplier / farm, other periods
    'E': ('Peer statistics', 0.65),               # similar items elsewhere
    'F': ('Model judgement', 0.5),                # an AI's educated guess, always labelled
    'G': ('Human decision', 1.0),
}
ORDER = 'GABCDEF'  # a human decision outranks everything; then A..F


def stronger(a: str, b: str) -> str:
    return a if ORDER.index(a) <= ORDER.index(b) else b


@dataclass
class Evidence:
    level: str
    source: str          # table / register / rule it comes from
    statement: str       # the computed fact, in words
    value: float | str | None = None

    def row(self) -> dict:
        return asdict(self)


# Known data-entry error mechanisms: (id, description, factor applied to the observed value).
MECHANISMS: list[tuple[str, str, float]] = [
    ('none', 'no error: the value is right', 1.0),
    ('unit_x1000', 'unit slip: value is 1000x too small (e.g. tonnes keyed as kg)', 1000.0),
    ('unit_div1000', 'unit slip: value is 1000x too large (e.g. kWh in a MWh column, grams as kg)', 0.001),
    ('decimal_x10', 'decimal slip: a digit missing', 10.0),
    ('decimal_div10', 'decimal slip: an extra digit', 0.1),
    ('decimal_x100', 'decimal slip: two digits missing', 100.0),
    ('decimal_div100', 'decimal slip: two extra digits', 0.01),
    ('sek_as_eur', 'currency: a SEK amount booked as EUR', 1 / 11.4),
    ('usd_as_eur', 'currency: a USD amount booked as EUR', 1 / 1.08),
]


@dataclass
class Hypothesis:
    mechanism: str
    description: str
    proposed: float
    misfit: float  # relative distance from the evidence value

    def row(self) -> dict:
        d = asdict(self)
        d['proposed'] = round(d['proposed'], 6)
        d['misfit'] = round(d['misfit'], 4)
        return d


def explain(observed: float, reference: float, allowed: set[str] | None = None,
            band: tuple[float, float] | None = None) -> list[Hypothesis]:
    """Every mechanism's corrected value and how far it lands from the evidence, best first.
    With a band (the observed range of a naturally variable quantity, e.g. refrigerant top-ups),
    the misfit is the distance outside that range; otherwise the distance from the reference."""
    if not reference or observed is None:
        return []
    out = []
    for mid, desc, f in MECHANISMS:
        if allowed is not None and mid not in allowed and mid != 'none':
            continue
        v = observed * f
        if band and band[0] > 0:
            lo, hi = band
            miss = 0.0 if lo <= v <= hi else (v / hi - 1 if v > hi else lo / v - 1)
        else:
            miss = abs(v - reference) / abs(reference)
        out.append(Hypothesis(mid, desc, v, miss))
    return sorted(out, key=lambda h: h.misfit)


# How close a mechanism must land to the evidence to count as a fit. Exact records (A–C) must
# match within 2 %; history and peer statistics are themselves variable, so they allow more.
TOLERANCE = {'A': 0.02, 'B': 0.02, 'C': 0.02, 'D': 0.35, 'E': 0.5, 'F': 0.5, 'G': 0.0}


def confidence(level: str, hyps: list[Hypothesis] | None = None) -> float:
    """Base confidence of the evidence level, discounted when no mechanism fits the evidence
    or when two mechanisms fit equally well."""
    base = LEVELS[level][1]
    if not hyps:
        return base
    tol = TOLERANCE[level]
    best = hyps[0]
    runner = hyps[1] if len(hyps) > 1 else None
    if best.misfit > tol:
        return round(base * 0.75, 3)  # evidence says "wrong", but no known mechanism explains it
    if runner and runner.misfit <= tol:
        return round(base * 0.7, 3)   # ambiguous between two explanations
    return base
