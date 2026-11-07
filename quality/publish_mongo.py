"""Publish the latest pipeline run (quality/out/) to MongoDB Atlas.

    python3 -m quality.pipeline && python3 -m quality.publish_mongo

MONGODB_URI / MONGODB_DB come from frontend/.env or the environment.

    dev_runs        one document per run: method, per-series noise and counts, scores, totals, scatter points
    dev_items       every flagged number: recorded, expected, gap, options with tonnes at stake, status
    dev_decisions   a person's choices from the app's Dev tab (written by the app, append-only;
                    the next pipeline run applies them)
    inventory       2023–2025 by scope and category, curated and raw
    proc_*          the corrected tables (latest run replaces the previous)
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
    items = json.loads((OUT / 'items.json').read_text())
    points = json.loads((OUT / 'points.json').read_text())
    inventory = json.loads((OUT / 'inventory.json').read_text())
    run_id = summary['runAt'].replace('-', '').replace(':', '').replace('+0000', 'Z')
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip()

    db = MongoClient(uri, appName='bluesky-curation', serverSelectionTimeoutMS=10000)[dbname]
    if db.dev_runs.find_one({'runId': run_id}):
        raise SystemExit(f'Run {run_id} is already published.')
    db.dev_runs.insert_one(bson_safe({**summary, 'runId': run_id, 'gitCommit': commit, 'points': points}))
    db.dev_items.insert_many([bson_safe({**i, 'itemKey': i['key'], 'runId': run_id}) for i in items])
    db.inventory.insert_many([bson_safe({**r, 'runId': run_id}) for r in inventory])

    sizes = {}
    for p in sorted((OUT / 'processed').glob('*.parquet')):
        name = f'proc_{p.stem}'
        docs = [bson_safe({**r, 'runId': run_id}) for r in pd.read_parquet(p).to_dict('records')]
        db[name].delete_many({})
        for i in range(0, len(docs), 5000):
            db[name].insert_many(docs[i:i + 5000])
        sizes[name] = len(docs)

    db.dev_items.create_index([('runId', DESCENDING), ('at_stake', DESCENDING)])
    db.dev_items.create_index([('itemKey', ASCENDING)])
    db.dev_decisions.create_index([('itemKey', ASCENDING), ('at', ASCENDING)])
    db.dev_runs.create_index([('runAt', DESCENDING)])
    db.inventory.create_index([('runId', DESCENDING), ('year', ASCENDING)])

    stats = db.command('dbStats')
    print(f'Published run {run_id}: {len(items)} items, {len(points)} scatter points, {len(inventory)} inventory rows')
    print('Processed tables:', sizes)
    print(f"Database: {stats['dataSize'] / 1e6:.1f} MB of the free tier's 512 MB")


if __name__ == '__main__':
    sys.path.insert(0, str(REPO))
    main()
