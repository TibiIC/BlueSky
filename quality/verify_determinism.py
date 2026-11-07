"""Runs the deterministic part of the pipeline (rules, evidence, corrections, inventory; the AI
layer switched off) twice in separate processes and checks the outputs are identical.

    python3 -m quality.verify_determinism [--package PATH]

Same raw package in -> same findings, same corrections, same inventory out, byte for byte.
No randomness, no models, no network: the detection is plain arithmetic on the data.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(out: Path, extra: list[str]) -> dict:
    subprocess.run([sys.executable, '-m', 'quality.pipeline', '--out', str(out), '--no-ai', *extra], cwd=REPO, check=True, capture_output=True)
    return json.loads((out / 'summary.json').read_text())['fingerprints']


def main():
    extra = sys.argv[1:]
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        fa, fb = run(Path(a), extra), run(Path(b), extra)
        files_equal = all((Path(a) / n).read_bytes() == (Path(b) / n).read_bytes()
                          for n in ('findings.json', 'checked.json', 'A1_issues_submission.csv', 'A2_inventory_2025_submission.csv'))
    for k in fa:
        print(f"{k:16} run 1 {fa[k][:16]}…  run 2 {fb[k][:16]}…  {'identical' if fa[k] == fb[k] else 'DIFFERENT'}")
    print(f"Output files byte-identical: {files_equal}")
    if fa != fb or not files_equal:
        raise SystemExit('NOT deterministic')
    print('Deterministic: two independent runs produced identical results.')


if __name__ == '__main__':
    main()
