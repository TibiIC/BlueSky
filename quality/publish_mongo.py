"""Publish the latest pipeline run (quality/out/) to MongoDB Atlas.

    python3 -m quality.pipeline && python3 -m quality.publish_mongo

Reads exactly what the pipeline wrote, so the database always matches the run that produced the
scores. MONGODB_URI / MONGODB_DB come from frontend/.env or the environment.

  Back office (history kept, one runId per run)
    dq_runs        run summary: scores on the public answers, counts by level and status, range
    dq_findings    every finding: evidence levels, competing explanations, impact, status, AI note
    dq_checked     legitimate look-alikes that were checked and left alone
    inventory      2023–2025 by scope and category, corrected and uncorrected
    dq_reviews     expert decisions (written by the app, append-only)

  Processed data (latest run replaces the previous; each row carries its runId)
    proc_energy, proc_purchases, proc_refrigerants, proc_goo, proc_shipments, proc_waste,
    proc_travel, proc_farm_footprints, proc_farm_survey
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / 'quality/out'


def env(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    f = REPO / 'frontend/.env'
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip().startswith(f'{name}='):
                return line.split('=', 1)[1].strip()
    return default


def bson_safe(v):
    """NaN -> None, numpy scalars -> Python, recursively."""
    if isinstance(v, dict):
        return {str(k): bson_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [bson_safe(x) for x in v]
    if hasattr(v, 'item') and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def main():
    uri, dbname = env('MONGODB_URI'), env('MONGODB_DB', 'bluesky')
    if not uri or '<db_password>' in uri:
        raise SystemExit('MONGODB_URI not set (frontend/.env).')
    if not (OUT / 'summary.json').exists():
        raise SystemExit('No run found: python3 -m quality.pipeline first.')
    from pymongo import ASCENDING, DESCENDING, MongoClient

    summary = json.loads((OUT / 'summary.json').read_text())
    findings = json.loads((OUT / 'findings.json').read_text())
    checked = json.loads((OUT / 'checked.json').read_text())
    inventory = json.loads((OUT / 'inventory.json').read_text())
    run_id = summary['runAt'].replace('-', '').replace(':', '').replace('+0000', 'Z')
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip()

    db = MongoClient(uri, appName='bluesky-quality', serverSelectionTimeoutMS=10000)[dbname]
    if db.dq_runs.find_one({'runId': run_id}):
        raise SystemExit(f'Run {run_id} is already published.')
    db.dq_runs.insert_one(bson_safe({**{k: summary[k] for k in summary if k not in ('inventory',)}, 'runId': run_id, 'gitCommit': commit,
                                     'inventoryRange': summary['inventory'].get('range'),
                                     'method': 'quality/METHOD.md: evidence levels A–G, error-mechanism library, code-tested AI layer'}))
    for f in findings:
        f['locator'] = {k: v for k, v in (f.get('locator') or {}).items() if k != 'row'}
        f['findingKey'] = f"{f['record_key']}|{f['issue_type']}"
        f['runId'] = run_id
        for k in ('observed', 'proposed'):
            if f.get(k) is not None and not isinstance(f[k], (int, float, str, list)):
                f[k] = str(f[k])
    db.dq_findings.insert_many([bson_safe(f) for f in findings])
    db.dq_checked.insert_many([bson_safe({**c, 'runId': run_id}) for c in checked])
    db.inventory.insert_many([bson_safe({**r, 'runId': run_id}) for r in inventory])

    sizes = {}
    for p in sorted((OUT / 'processed').glob('*.parquet')):
        name = f'proc_{p.stem}'
        df = pd.read_parquet(p)
        db[name].delete_many({})
        docs = [bson_safe({**r, 'runId': run_id}) for r in df.to_dict('records')]
        for i in range(0, len(docs), 5000):
            db[name].insert_many(docs[i:i + 5000])
        sizes[name] = len(docs)

    db.dq_findings.create_index([('runId', DESCENDING), ('priority', DESCENDING)])
    db.dq_findings.create_index([('findingKey', ASCENDING)])
    db.inventory.create_index([('runId', DESCENDING), ('year', ASCENDING)])
    db.dq_reviews.create_index([('findingKey', ASCENDING), ('at', ASCENDING)])
    db.dq_runs.create_index([('runAt', DESCENDING)])

    stats = db.command('dbStats')
    print(f'Published run {run_id}: {len(findings)} findings, {len(checked)} checked, {len(inventory)} inventory rows')
    print('Processed tables:', sizes)
    print(f"Database: {stats['dataSize'] / 1e6:.1f} MB of the free tier's 512 MB")


if __name__ == '__main__':
    sys.path.insert(0, str(REPO))
    main()
