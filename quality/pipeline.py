"""Data-quality pipeline: raw feeds -> findings -> corrected copy -> inventory, with scores.

    python3 -m quality.pipeline [--package PATH] [--out DIR]

1. Load the raw package (ccn_tools.io.load_raw) plus the GoO registry statement.
2. Run every rule in quality.rules -> findings (with rule, evidence, confidence, proposal).
3. Apply the automatic corrections (correct / drop / add) to a copy. `flag` findings change
   nothing, except soil: every farm's organic share comes from the soil map.
4. Compute the inventory with the package's reference calculator on the corrected copy, and on
   the uncorrected data for comparison.
5. Score error detection (A1) and the inventory (A2) on the public 2023–2024 answers.
6. Write findings, corrections, inventories, scores and the 2025 submission CSVs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = Path.home() / 'Downloads/Apetit_SinceAI2026 _1_/Apetit_SinceAI2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026'
DEFAULT_OUT = REPO / 'quality/out'
DEV_YEARS = (2023, 2024)
CROP_MAT = {'M100': 'turnip_rape', 'M110': 'pea', 'M111': 'potato', 'M112': 'carrot', 'M113': 'spinach'}


def load(pkg: Path):
    sys.path.insert(0, str(pkg / 'tools'))
    from ccn_tools import io as IO, reference_calculator as RC, score as SC  # noqa: E402
    raw = IO.load_raw(pkg)
    raw['goo_registry'] = pd.read_csv(pkg / 'data/02_raw_feeds/goo_registry_statement.csv')
    raw['capex'] = pd.read_csv(pkg / 'data/02_raw_feeds/capex_projects.csv')
    return raw, IO, RC, SC


def run_rules(raw):
    from quality.rules import RULES, TABLES  # noqa: F401
    checked, findings = [], []
    for name, fn in RULES:
        findings += fn(raw, checked)
    # No de-duplication here: quality.assess merges every rule's evidence about the same record.
    return findings, checked


def apply(raw: dict, findings) -> dict:
    """Corrected copy of the raw tables. Raw stays untouched."""
    from quality.rules import TABLES
    out = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in raw.items()}
    drops: dict[str, set] = {}
    adds: dict[str, list] = {}
    for f in findings:
        t = TABLES.get(f.table)
        if t is None or f.action == 'flag':
            continue
        df = out[t]
        if f.action == 'correct':
            i = f.locator['index']
            if f.field == 'lat,lon':
                df.loc[i, ['lat', 'lon']] = f.proposed
            else:
                df.loc[i, f.field] = f.proposed
        elif f.action == 'drop':
            if 'index' in f.locator:
                drops.setdefault(t, set()).add(f.locator['index'])
            elif 'file' in f.locator:
                out[t] = df[df.file != f.locator['file']]
        elif f.action == 'add' and f.locator.get('row') and f.proposed is not None:
            adds.setdefault(t, []).append(f.locator['row'])
    for t, idx in drops.items():
        out[t] = out[t].drop(index=list(idx))
    for t, rows in adds.items():
        out[t] = pd.concat([out[t], pd.DataFrame(rows)], ignore_index=True)
    return out


def organic_share(raw) -> pd.Series:
    """Share of each farm's crop area on organic soil per year, from the soil map."""
    hp = raw['crop_history'].merge(raw['parcels'][['parcel_id', 'area_ha', 'soil_class_soilmap']], on='parcel_id')
    hp['org'] = hp.area_ha.where(hp.soil_class_soilmap == 'organic', 0.0)
    s = hp.groupby(['farm_id', 'crop', 'year'])[['org', 'area_ha']].sum()
    return s.org / s.area_ha


def farm_footprints(raw, erp: pd.DataFrame, use_soil_map: bool) -> pd.DataFrame:
    """Contract-farm emissions allocated to delivered kg (METHODOLOGY §5). The footprint per ha
    blends mineral and organic soil by the soil-map organic share instead of trusting the
    survey's single soil answer. Non-respondents get the crop-year production-weighted intensity."""
    from ccn_tools.farm_calculator import farm_footprint_per_ha
    sv = raw['farm_survey'].copy()
    if use_soil_map:
        share = organic_share(raw)
        sv['share'] = [share.get((f, c, y), np.nan) for f, c, y in zip(sv.farm_id, sv.crop, sv.year)]
        sv['share'] = sv.share.fillna(sv.soil_type_reported.str.lower().str.startswith('organic').astype(float))
        mineral = farm_footprint_per_ha(sv.assign(organic_soil=False))
        organic = farm_footprint_per_ha(sv.assign(organic_soil=True))
        sv['kg_ha'] = mineral + sv.share.values * (organic - mineral)
    else:
        sv['organic_soil'] = sv.soil_type_reported.str.lower().str.startswith('organic')
        sv['kg_ha'] = farm_footprint_per_ha(sv)
    sv['kg_per_kg'] = sv.kg_ha / (sv.yield_t_ha * 1000)
    d = erp[erp.material_id.isin(CROP_MAT)].copy()
    d['crop'] = d.material_id.map(CROP_MAT)
    d = d.groupby(['supplier_id', 'crop', 'year']).qty_kg.sum().reset_index().rename(columns={'supplier_id': 'farm_id'})
    d = d.merge(sv[['farm_id', 'crop', 'year', 'kg_per_kg']], on=['farm_id', 'crop', 'year'], how='left')
    # Non-respondents: the respondents' production-weighted intensity (total emissions / total
    # production), the right average for emissions allocated per kg. A median would understate it,
    # since a few peat farms skew the distribution.
    sv['_w'] = sv.area_ha * sv.yield_t_ha
    med = sv.dropna(subset=['kg_per_kg']).groupby(['crop', 'year']).apply(
        lambda g: np.average(g.kg_per_kg, weights=g._w), include_groups=False)
    d['kg_per_kg'] = d.kg_per_kg.fillna(pd.Series(list(zip(d.crop, d.year))).map(med))
    d['tco2e'] = d.qty_kg * d.kg_per_kg / 1000
    d['region'] = 'FI_SW'
    return d[['farm_id', 'crop', 'year', 'region', 'tco2e']]


def inventory(raw, IO, RC, years, corrected: bool) -> dict[int, pd.DataFrame]:
    T = IO.naive_canonical(raw)
    T['farm_footprints'] = farm_footprints(raw, T['purchases'], use_soil_map=corrected)
    return {y: RC.summarise(RC.compute_inventory(T, y)) for y in years}


def fingerprint(obj) -> str:
    """SHA-256 of a canonical JSON rendering (sorted keys, fixed float formatting). Two runs on
    the same package give the same fingerprint, or the pipeline is not deterministic."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


# Findings that go into the 2025 error list: confirmed or proposed corrections, and flags whose
# evidence makes an error more likely than not. Unexplained anomalies are not submitted.
def submitted(f) -> bool:
    return f.status in ('confirmed', 'proposed') or (f.status == 'needs_review' and f.confidence >= 0.6)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--package', type=Path, default=Path(os.environ.get('APETIT_PACKAGE', DEFAULT_PACKAGE)))
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--no-ai', action='store_true', help='skip the AI layer even if ANTHROPIC_API_KEY is set')
    ap.add_argument('--ai-limit', type=int, default=60, help='max review-queue items sent to the model')
    args = ap.parse_args()
    pkg, out = args.package, args.out
    out.mkdir(parents=True, exist_ok=True)

    from quality.assess import assess, inventory_range, review_queue
    from quality.rules import TABLES, report_total_check
    raw, IO, RC, SC = load(pkg)

    # 1–2. rules -> merged, evidence-graded findings
    found, checked = run_rules(raw)
    findings = assess(found, raw)
    det_fp = fingerprint(sorted(({k: v for k, v in f.row().items() if k != 'ai'} for f in findings),
                                key=lambda d: (d['record_key'], d['issue_type'], str(d['field']))))

    # 3. AI layer: hypotheses for unexplained anomalies, notes for the review queue (optional)
    from quality.ai import AI
    ai = AI(enabled=not args.no_ai)

    def record(f):
        t, i = TABLES.get(f.table), f.locator.get('index')
        return raw[t].loc[i].to_dict() if t and i is not None and i in raw[t].index else {}
    if ai.available:
        for f in [f for f in findings if f.status == 'unexplained']:
            ai.hypothesize(f, record(f))
        for f in review_queue(findings, args.ai_limit):
            ai.review(f, record(f))
        ai.save()

    # 4–5. corrected copy -> inventory
    clean = apply(raw, findings)
    years = (2023, 2024, 2025)
    inv_clean = inventory(clean, IO, RC, years, corrected=True)
    inv_raw = inventory(raw, IO, RC, years, corrected=False)
    comp25 = dict(zip(inv_clean[2025].category, inv_clean[2025].tco2e))  # totals have unique category names
    findings += assess(report_total_check(pd.read_csv(pkg / 'data/05_scenarios/draft_report_summary_2025.csv'), comp25), raw)
    rng = {y: inventory_range([f for f in findings if f.year == y]) for y in years}
    queue = review_queue(findings, 50)

    # 6. scores on the public answers
    key = pd.read_csv(pkg / 'tasks/dev/A1_dev_issue_labels_2023_2024.csv')
    fdf = pd.DataFrame([f.row() for f in findings])
    sub_mask = fdf.apply(lambda r: r.status in ('confirmed', 'proposed') or (r.status == 'needs_review' and r.confidence >= 0.6), axis=1)
    dev = fdf[fdf.year.isin(DEV_YEARS) & sub_mask]
    a1 = SC.score_a1(dev[['table', 'record_key', 'issue_type', 'year']], key, years=list(DEV_YEARS))

    def precision_by(col):
        res = {}
        for v, g in fdf[fdf.year.isin(DEV_YEARS)].groupby(col):
            tp = int(g.record_key.isin(key.record_key).sum())
            res[str(v)] = {'findings': int(len(g)), 'confirmedByAnswers': tp, 'precision': round(tp / len(g), 3)}
        return res
    a2 = {}
    for y in DEV_YEARS:
        k2 = pd.read_csv(pkg / f'tasks/dev/A2_dev_inventory_{y}.csv')
        a2[y] = {'corrected': SC.score_a2(inv_clean[y], k2), 'raw': SC.score_a2(inv_raw[y], k2)}

    # 7. outputs
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    y25 = fdf[(fdf.year == 2025) & sub_mask]
    y25.assign(explanation=y25.evidence)[['table', 'record_key', 'issue_type', 'confidence', 'explanation']].to_csv(out / 'A1_issues_submission.csv', index=False)
    tmpl = pd.read_csv(pkg / 'tasks/templates/A2_inventory_2025_submission.csv')
    a2sub = tmpl.drop(columns=[c for c in ('tco2e',) if c in tmpl]).merge(inv_clean[2025][['scope', 'category', 'tco2e']], on=['scope', 'category'], how='left')
    a2sub.to_csv(out / 'A2_inventory_2025_submission.csv', index=False)

    def inv_json(d):
        # scope:category, since e.g. purchased_electricity exists under both Scope 2 methods
        return {str(y): {f'{sc}:{c}': round(float(x), 2) for sc, c, x in zip(v.scope, v.category, v.tco2e)} for y, v in d.items()}
    summary = {
        'runAt': stamp,
        'fingerprints': {
            'deterministicFindings': det_fp,
            'inventory2025': fingerprint({f'{a}:{b}': round(float(c), 6) for a, b, c in zip(inv_clean[2025].scope, inv_clean[2025].category, inv_clean[2025].tco2e)}),
            'packageManifest': hashlib.sha256((pkg / 'MANIFEST.json').read_bytes()).hexdigest(),
        },
        'package': json.loads((pkg / 'MANIFEST.json').read_text()).get('version'),
        'counts': {
            'findings': len(findings),
            'byType': fdf.groupby('issue_type').size().to_dict(),
            'byLevel': fdf.groupby('level').size().to_dict(),
            'byStatus': fdf.groupby('status').size().to_dict(),
            'byYear': {str(k): int(v) for k, v in fdf.groupby('year').size().items()},
            'checkedLegitimate': len(checked),
            'submitted2025': int(len(y25)),
        },
        'ai': {'model': 'claude-haiku-5-5', 'available': ai.available, 'calls': ai.calls, 'cached': len(ai.cache), 'errors': ai.errors[:5],
               'notes': int(sum(1 for f in findings if f.ai))},
        'scores': {
            'A1_dev': {k: a1[k] for k in ('score', 'precision', 'recall', 'f1', 'type_accuracy', 'n_flagged', 'n_true')},
            'A1_recall_by_type': a1['recall_by_type'],
            'A1_per_rule': precision_by('rule'),
            'A1_by_level': precision_by('level'),
            'A1_by_status': precision_by('status'),
            'A2_dev': {str(y): {'corrected': v['corrected']['score'], 'raw': v['raw']['score'],
                                'detail': v['corrected']['detail']} for y, v in a2.items()},
            'baselines': {'A1_dev': 52.17, 'A2_2023': 25.54, 'A2_2024': 23.24},
        },
        'inventory': {'corrected': inv_json(inv_clean), 'raw': inv_json(inv_raw), 'range': {str(y): r for y, r in rng.items()}},
        'reviewQueue': [{k: f.row()[k] for k in ('record_key', 'issue_type', 'year', 'level', 'status', 'confidence', 'impact_tco2e', 'priority')} for f in queue[:20]],
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, default=str))
    # Processed (corrected) tables and the inventory, exactly as used above: the publish step reads these.
    proc = out / 'processed'
    proc.mkdir(exist_ok=True)
    T = IO.naive_canonical(clean)
    T['farm_footprints'] = farm_footprints(clean, T['purchases'], use_soil_map=True)
    for name, df in {'energy': T['energy'], 'purchases': T['purchases'], 'refrigerants': clean['refrigerants'], 'goo': clean['goo'],
                     'shipments': clean['shipments'], 'waste': T['waste'], 'travel': clean['travel'],
                     'farm_footprints': T['farm_footprints'], 'farm_survey': clean['farm_survey']}.items():
        df.reset_index(drop=True).to_parquet(proc / f'{name}.parquet', index=False)
    inv_rows = []
    for y in years:
        m = inv_clean[y].merge(inv_raw[y], on=['scope', 'category'], how='outer', suffixes=('', '_uncorrected'))
        inv_rows += [{'year': y, 'scope': r.scope, 'category': r.category, 'tco2e': float(r.tco2e),
                      'tco2eUncorrected': None if pd.isna(r.tco2e_uncorrected) else float(r.tco2e_uncorrected)} for r in m.itertuples()]
    (out / 'inventory.json').write_text(json.dumps(inv_rows))
    (out / 'findings.json').write_text(json.dumps([f.row() for f in findings], default=str))
    (out / 'checked.json').write_text(json.dumps([c.__dict__ for c in checked], default=str))

    print(f"Findings: {len(findings)} · by level {summary['counts']['byLevel']} · by status {summary['counts']['byStatus']}")
    print(f"A1 dev score: {a1['score']} (baseline 52.17) · P {a1['precision']} R {a1['recall']} · type acc {a1['type_accuracy']}")
    print('Precision by evidence level (2023–24):', {k: v['precision'] for k, v in summary['scores']['A1_by_level'].items()})
    for y in DEV_YEARS:
        print(f"A2 {y}: corrected {a2[y]['corrected']['score']} vs raw {a2[y]['raw']['score']}")
    print(f"2025 range by scope: {rng[2025]}")
    print(f"AI: {'on' if ai.available else 'off (no ANTHROPIC_API_KEY)'} · calls {ai.calls} · errors {len(ai.errors)}")
    print(f'Wrote {out}')


if __name__ == '__main__':
    sys.path.insert(0, str(REPO))
    main()
