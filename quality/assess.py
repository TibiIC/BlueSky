"""Turns rule output into principled findings.

For each record and issue:
1. Merge what every rule found about it; keep all evidence, strongest level first.
2. Score the known error mechanisms against the evidence value (competing explanations,
   including "no error").
3. Set confidence from the evidence level and the fit margin.
4. Decide status: `confirmed` (A–C evidence with a fitting mechanism) is applied automatically;
   `proposed` (D–E) is applied to the best estimate but awaits review; `needs_review` (flags)
   changes nothing until an expert decides; `unexplained` anomalies go to the hypothesis layer.
5. Estimate the inventory impact and the review priority: |impact| x (1 - confidence).
"""
from __future__ import annotations

from quality.evidence import LEVELS, TOLERANCE, Evidence, confidence, explain
from quality.impact import Context, impact

# Evidence level each rule provides, by issue type where it differs.
LEVEL = {
    'erp.shipments': 'B', 'erp.capex': 'A', 'goo.registry': 'A', 'report.totals': 'B',
    'erp.material_text': 'C', 'travel.duplicate': 'C', 'commuting.survey': 'C', 'farm.coordinates': 'C',
    'erp.duplicate': 'D', 'energy.meter': 'D', 'fuel.units': 'D', 'waste.units': 'D', 'refrigerant.log': 'D',
    'shipments.legs': 'D', 'erp.unit_price': 'E', 'farm.soil': 'E',
}
LEVEL_BY_ISSUE = {
    ('erp.currency', 'currency'): 'D',        # the supplier's own invoicing history
    ('erp.currency', 'net_amount'): 'E',      # amount vs the supplier's typical amount
    ('farm.survey', 'area_ha'): 'B',          # the parcel register is an independent record
    ('farm.survey', 'yield_t_ha'): 'E', ('farm.survey', 'n_mineral_kg_ha'): 'E',
    ('pcf.validity', None): 'C',              # validity rule from the method (period must cover the year)
}
ALLOWED = {
    'unit_error': {'unit_x1000', 'unit_div1000'},
    'decimal_shift': {'decimal_x10', 'decimal_div10', 'decimal_x100', 'decimal_div100'},
    'currency_error': {'sek_as_eur', 'usd_as_eur'},
    'meter_spike': {'unit_x1000', 'unit_div1000', 'decimal_x10', 'decimal_div10'},
    'outlier_implausible': None,  # all mechanisms
}
SOURCE_TABLE = {
    'erp.shipments': 'shipments.csv (inbound legs)', 'erp.capex': 'capex_projects.csv (register)', 'goo.registry': 'goo_registry_statement.csv',
    'farm.survey': 'parcel register + survey', 'report.totals': 'computed inventory',
}


def level_of(f) -> str:
    if f.locator.get('level'):
        return f.locator['level']
    if (f.rule, f.field) in LEVEL_BY_ISSUE:
        return LEVEL_BY_ISSUE[(f.rule, f.field)]
    if f.rule == 'pcf.validity':
        return 'C' if f.issue_type == 'pcf_stale_period' else 'D'
    return LEVEL.get(f.rule, 'E')


def hyps_none(hyps):
    return next((h for h in hyps if h.mechanism == 'none'), None)


def decisive(hyps, level) -> bool:
    """History or peer evidence becomes decisive when "no error" is implausible (the value is more
    than 10x off) AND one known mechanism lands within the level's tolerance (unit and decimal
    slips are exact powers of ten, so this cannot happen by chance)."""
    if not hyps or level not in ('D', 'E'):
        return False
    n, best = hyps_none(hyps), hyps[0]
    if n is None or best.mechanism == 'none':
        return False
    if n.misfit > 10 and best.misfit <= TOLERANCE[level]:
        return True
    # Order-of-magnitude test for unit slips (factors of 1000): more than 100x off before the fix,
    # within 10x after. A second, smaller problem (e.g. a spike) may remain and is its own finding.
    return best.mechanism.startswith('unit_') and n.misfit > 100 and best.misfit <= 9


def merge(findings):
    groups: dict[tuple, list] = {}
    for f in findings:
        groups.setdefault((f.record_key, f.issue_type), []).append(f)
    merged = []
    for (key, itype), fs in groups.items():
        real = [f for f in fs if not f.locator.get('supporting')]
        if not real:  # only supporting evidence (e.g. a receipt with no shipment): keep it as a flag
            real = fs
        fs_sorted = sorted(fs, key=lambda f: 'GABCDEF'.index(level_of(f)))
        lead = sorted(real, key=lambda f: 'GABCDEF'.index(level_of(f)))[0]
        lead.sources = [Evidence(level_of(f), SOURCE_TABLE.get(f.rule, f.rule), f.evidence, f.locator.get('reference')).row() for f in fs_sorted]
        lead.level = level_of(fs_sorted[0])  # the strongest evidence any rule brought
        merged.append(lead)
    return merged


def assess(findings, raw):
    ctx = Context(raw)
    out = merge(findings)
    for f in out:
        f.level = f.level or level_of(f)
        ref = f.locator.get('reference')
        hyps = []
        try:
            obs = float(f.observed) if f.observed is not None else None
        except (TypeError, ValueError):
            obs = None
        if ref and obs and f.issue_type in ALLOWED:
            hyps = explain(obs, float(ref), ALLOWED[f.issue_type], f.locator.get('band'))
        f.hypotheses = [h.row() for h in hyps]
        f.confidence = confidence(f.level, hyps) if f.action != 'flag' else round(min(f.confidence, LEVELS[f.level][1]), 3)
        if f.locator.get('unexplained'):
            f.status = 'unexplained'
        elif f.action == 'flag':
            f.status = 'needs_review'
        elif f.level in ('A', 'B', 'C') and (not hyps or (hyps[0].mechanism != 'none' and hyps[0].misfit <= TOLERANCE[f.level])):
            f.status = 'confirmed'
            f.locator['status_reason'] = f'level {f.level} evidence' + (f', explained by {hyps[0].mechanism}' if hyps else '')
        elif decisive(hyps, f.level):
            f.status = 'confirmed'
            f.locator['status_reason'] = (f'decisive: the value is {hyps_none(hyps).misfit + 1:.0f}x off the evidence and '
                                          f'{hyps[0].mechanism} lands within {hyps[0].misfit:.0%}')
        else:
            f.status = 'proposed'
        if f.issue_type == 'soil_misreport':
            # The inventory takes soil from the soil map for every farm (pipeline.farm_footprints), so
            # this flag's effect is already in the best estimate. A person still decides; if they side
            # with the farmer's answer, the effect is reverted. The range treats it like a proposal.
            f.locator['in_estimate'] = True
            f.locator['status_reason'] = 'soil map used in the footprint; reverts if a reviewer sides with the survey'
        try:
            scope, d = impact(f, ctx)
        except Exception:  # an estimate must never break the pipeline
            scope, d = None, None
        f.impact_tco2e = None if d is None else round(float(d), 3)
        f.locator['scope'] = scope
        uncertain = 1 - f.confidence if f.status != 'confirmed' else 0.0
        f.priority = round(abs(f.impact_tco2e or 0.0) * uncertain, 3)
    return out


def inventory_range(findings) -> dict:
    """How far the inventory could move if the uncertain calls were wrong. Anything already in the
    best estimate (`proposed` corrections, and flags whose effect the estimate already includes,
    such as soil from the soil map) is reverted; any other `needs_review` flag is assumed right.
    Confirmed corrections rest on A–C or decisive evidence and are not varied."""
    lo, hi = {}, {}
    for f in findings:
        if f.impact_tco2e is None or f.status not in ('proposed', 'needs_review'):
            continue
        in_estimate = f.status == 'proposed' or f.locator.get('in_estimate')
        d = -f.impact_tco2e if in_estimate else f.impact_tco2e
        s = (f.locator.get('scope') or 'other').split(':')[0]
        lo[s] = lo.get(s, 0.0) + min(0.0, d)
        hi[s] = hi.get(s, 0.0) + max(0.0, d)
    return {s: {'down': round(lo.get(s, 0.0), 1), 'up': round(hi.get(s, 0.0), 1)} for s in sorted(set(lo) | set(hi))}


def review_queue(findings, n=50):
    q = [f for f in findings if f.status in ('needs_review', 'proposed', 'unexplained')]
    return sorted(q, key=lambda f: (-f.priority, f.record_key))[:n]
