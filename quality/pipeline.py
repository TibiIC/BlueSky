"""Curation pipeline: raw data -> gaps -> corrected copy -> footprint, with scores.

    python3 -m quality.pipeline [--package PATH] [--out DIR] [--no-decisions]

1. Load the raw package.
2. quality.gaps: predict every number, flag the gaps, fix obvious typos, rank the rest by
   tonnes at stake (see quality/METHOD.md).
3. Apply the fixes to a copy, plus every decision a person made in the app's Dev tab
   (MongoDB `dev_decisions`). Raw data is never changed.
4. Footprint with the package's reference calculator, on the corrected copy and on raw data.
5. Score on the organisers' published 2023–2024 answers; write the 2025 submission files.
"""
from __future__ import annotations

import argparse
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
YEARS = (2023, 2024, 2025)
CROP_MAT = {'M100': 'turnip_rape', 'M110': 'pea', 'M111': 'potato', 'M112': 'carrot', 'M113': 'spinach'}
BASELINES = {'A1_dev': 52.17, 'A2_2023': 25.54, 'A2_2024': 23.24}


def load(pkg: Path):
    sys.path.insert(0, str(pkg / 'tools'))
    from ccn_tools import io as IO, reference_calculator as RC, score as SC  # noqa: E402
    raw = IO.load_raw(pkg)
    raw['goo_registry'] = pd.read_csv(pkg / 'data/02_raw_feeds/goo_registry_statement.csv')
    return raw, IO, RC, SC


def farm_footprints(raw, erp: pd.DataFrame, use_soil_map: bool, keep_soil: set = frozenset()) -> pd.DataFrame:
    """Contract-farm emissions allocated to delivered kg (METHODOLOGY §5). With the soil map, the
    footprint per ha blends mineral and peat soil by the map's peat share, except for surveys where
    a reviewer kept the farmer's answer. Non-respondents get the production-weighted intensity."""
    from ccn_tools.farm_calculator import farm_footprint_per_ha
    from quality.gaps import organic_share
    sv = raw['farm_survey'].copy()
    reported = sv.soil_type_reported.str.lower().str.startswith('organic').astype(float)
    if use_soil_map:
        share = organic_share(raw)
        sv['share'] = [share.get((f, c, y), np.nan) for f, c, y in zip(sv.farm_id, sv.crop, sv.year)]
        sv['share'] = sv.share.fillna(reported).where(~sv.survey_id.isin(keep_soil), reported)
        mineral = farm_footprint_per_ha(sv.assign(organic_soil=False))
        organic = farm_footprint_per_ha(sv.assign(organic_soil=True))
        sv['kg_ha'] = mineral + sv.share.values * (organic - mineral)
    else:
        sv['organic_soil'] = reported.astype(bool)
        sv['kg_ha'] = farm_footprint_per_ha(sv)
    sv['kg_per_kg'] = sv.kg_ha / (sv.yield_t_ha * 1000)
    d = erp[erp.material_id.isin(CROP_MAT)].copy()
    d['crop'] = d.material_id.map(CROP_MAT)
    d = d.groupby(['supplier_id', 'crop', 'year']).qty_kg.sum().reset_index().rename(columns={'supplier_id': 'farm_id'})
    d = d.merge(sv[['farm_id', 'crop', 'year', 'kg_per_kg']], on=['farm_id', 'crop', 'year'], how='left')
    # Non-respondents: total emissions / total production of the respondents (crop, year): the right
    # average for emissions allocated per kg.
    sv['_w'] = sv.area_ha * sv.yield_t_ha
    med = sv.dropna(subset=['kg_per_kg']).groupby(['crop', 'year']).apply(
        lambda g: np.average(g.kg_per_kg, weights=g._w), include_groups=False)
    d['kg_per_kg'] = d.kg_per_kg.fillna(pd.Series(list(zip(d.crop, d.year))).map(med))
    d['tco2e'] = d.qty_kg * d.kg_per_kg / 1000
    d['region'] = 'FI_SW'
    return d[['farm_id', 'crop', 'year', 'region', 'tco2e']]


def footprint(raw, IO, RC, corrected: bool, keep_soil: set = frozenset()):
    T = IO.naive_canonical(raw)
    T['farm_footprints'] = farm_footprints(raw, T['purchases'], use_soil_map=corrected, keep_soil=keep_soil)
    return T, {y: RC.summarise(RC.compute_inventory(T, y)) for y in YEARS}


def load_decisions() -> dict:
    """The latest decision per number from the app's Dev tab (MongoDB), if a database is configured."""
    from quality.publish_mongo import env
    uri = env('MONGODB_URI')
    if not uri or '<db_password>' in uri:
        return {}
    try:
        from pymongo import MongoClient
        db = MongoClient(uri, serverSelectionTimeoutMS=8000)[env('MONGODB_DB', 'bluesky')]
        latest = {}
        for d in db.dev_decisions.find({}, {'_id': 0, 'itemKey': 1, 'choice': 1}).sort('at', 1):
            latest[d['itemKey']] = d['choice']
        return latest
    except Exception as e:  # the pipeline must run offline too
        print(f'Decisions not loaded ({type(e).__name__}); using defaults.')
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--package', type=Path, default=Path(os.environ.get('APETIT_PACKAGE', DEFAULT_PACKAGE)))
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--no-decisions', action='store_true', help='ignore decisions saved in the app')
    ap.add_argument('--no-ai', action='store_true', help='skip the one-sentence explanations even if ANTHROPIC_API_KEY is set')
    ap.add_argument('--ai-limit', type=int, default=250, help='max items explained (most tonnes at stake first)')
    args = ap.parse_args()
    pkg, out = args.package, args.out
    out.mkdir(parents=True, exist_ok=True)

    from quality import gaps
    raw, IO, RC, SC = load(pkg)
    items, points, meta = gaps.evaluate(raw)
    from quality.ai import AI, MODEL
    ai = AI(enabled=not args.no_ai)
    ai.explain(items, meta, args.ai_limit)
    ai.save()
    decisions = {} if args.no_decisions else load_decisions()
    clean, keep_soil = gaps.apply(raw, items, decisions)
    T, inv = footprint(clean, IO, RC, corrected=True, keep_soil=keep_soil)
    _, inv_raw = footprint(raw, IO, RC, corrected=False)

    # Scores on the published 2023–2024 answers
    df = pd.DataFrame([i.row() for i in items])
    key = pd.read_csv(pkg / 'tasks/dev/A1_dev_issue_labels_2023_2024.csv')
    dev = df[df.year.isin(DEV_YEARS)].drop_duplicates(['record_key', 'issue_type'])
    a1 = SC.score_a1(dev[['table', 'record_key', 'issue_type', 'year']], key, years=list(DEV_YEARS))
    by_series = {s: {'flagged': int(len(g)), 'inAnswers': int(g.record_key.isin(key.record_key).sum())}
                 for s, g in dev.groupby('series')}
    by_status = {s: {'flagged': int(len(g)), 'inAnswers': int(g.record_key.isin(key.record_key).sum())}
                 for s, g in dev.groupby('status')}
    a2 = {y: {'curated': SC.score_a2(inv[y], pd.read_csv(pkg / f'tasks/dev/A2_dev_inventory_{y}.csv'))['score'],
              'raw': SC.score_a2(inv_raw[y], pd.read_csv(pkg / f'tasks/dev/A2_dev_inventory_{y}.csv'))['score']} for y in DEV_YEARS}

    # 2025 submission files
    y25 = df[df.year == 2025].drop_duplicates(['record_key', 'issue_type'])
    conf = y25.status.map({'fixed': 0.95, 'check': 0.7})
    y25.assign(confidence=conf, explanation=y25.explanation)[['table', 'record_key', 'issue_type', 'confidence', 'explanation']] \
        .to_csv(out / 'A1_issues_submission.csv', index=False)
    tmpl = pd.read_csv(pkg / 'tasks/templates/A2_inventory_2025_submission.csv')
    tmpl.drop(columns=[c for c in ('tco2e',) if c in tmpl]).merge(inv[2025][['scope', 'category', 'tco2e']], on=['scope', 'category'], how='left') \
        .to_csv(out / 'A2_inventory_2025_submission.csv', index=False)

    def totals(d):
        return {str(y): {c: round(float(t), 2) for sc, c, t in zip(v.scope, v.category, v.tco2e) if sc == 'total'} for y, v in d.items()}

    open_t = {str(y): round(sum(abs(i.tco2e) for i in items if i.year == y and i.status == 'check' and i.key not in decisions), 1) for y in YEARS}
    summary = {
        'runAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'method': 'Predict what every number should be, rank the gaps by tonnes of CO2 at stake, a person checks the top.',
        'series': meta,
        'counts': {'items': len(items), 'fixed': int((df.status == 'fixed').sum()), 'check': int((df.status == 'check').sum()),
                   'decided': sum(1 for i in items if i.key in decisions),
                   'byYear': {str(k): int(v) for k, v in df.groupby('year').size().items()}},
        'awaitingTonnes': open_t,
        'ai': {'model': MODEL, 'available': ai.available, 'sentences': sum(1 for i in items if i.ai), 'calls': ai.calls, 'errors': ai.errors[:5]},
        'scores': {'A1_dev': {k: a1[k] for k in ('score', 'precision', 'recall', 'f1', 'type_accuracy', 'n_flagged', 'n_true')},
                   'A1_recall_by_type': a1['recall_by_type'], 'bySeries': by_series, 'byStatus': by_status,
                   'A2_dev': {str(y): v for y, v in a2.items()}, 'baselines': BASELINES},
        'totals': {'curated': totals(inv), 'raw': totals(inv_raw)},
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, default=str))
    (out / 'items.json').write_text(json.dumps([dict(i.row(), inForce=gaps.choice(i, decisions)) for i in items], default=str))
    (out / 'points.json').write_text(json.dumps(points))

    proc = out / 'processed'
    proc.mkdir(exist_ok=True)
    for old in proc.glob('*.parquet'):
        old.unlink()
    for name, d in {'energy': T['energy'], 'purchases': T['purchases'], 'refrigerants': clean['refrigerants'], 'fuel': clean['fuel_deliveries'],
                    'waste': T['waste'], 'pcfs': clean['pcfs'], 'farm_footprints': T['farm_footprints'], 'farm_survey': clean['farm_survey']}.items():
        d.reset_index(drop=True).to_parquet(proc / f'{name}.parquet', index=False)
    rows = []
    for y in YEARS:
        m = inv[y].merge(inv_raw[y], on=['scope', 'category'], how='outer', suffixes=('', '_raw'))
        rows += [{'year': y, 'scope': r.scope, 'category': r.category, 'tco2e': float(r.tco2e),
                  'tco2eRaw': None if pd.isna(r.tco2e_raw) else float(r.tco2e_raw)} for r in m.itertuples()]
    (out / 'inventory.json').write_text(json.dumps(rows))

    print(f"Items: {len(items)} · fixed automatically {summary['counts']['fixed']} · for a person {summary['counts']['check']} · decided {summary['counts']['decided']}")
    print('Flagged per series:', {k: v['flagged'] for k, v in meta.items()})
    print(f"A1 dev: {a1['score']} (baseline {BASELINES['A1_dev']}) · P {a1['precision']} R {a1['recall']} · type acc {a1['type_accuracy']}")
    for y in DEV_YEARS:
        print(f"A2 {y}: curated {a2[y]['curated']} vs raw {a2[y]['raw']} (baseline {BASELINES[f'A2_{y}']})")
    print('2025 totals:', summary['totals']['curated']['2025'], '· awaiting a person:', open_t['2025'], 't')
    print(f"AI: {'on' if ai.available else 'off (no ANTHROPIC_API_KEY)'} · sentences {summary['ai']['sentences']} · new calls {ai.calls} · errors {len(ai.errors)}")
    print(f'Wrote {out}')


if __name__ == '__main__':
    sys.path.insert(0, str(REPO))
    main()
