# Climate Lens report backend

Generates field-decision reports from the FinlandIP DSS notebook
(`notebooks/FinlandIP_DSS.ipynb`). The notebook's widget dashboard
(field playbook, escalation gate, cultivation plan, cost & carbon, breeding,
biotech, optional Gemini explanation) is served as one report, in JSON or as a
printable HTML page. All figures are illustrative.

## Run locally

Needs Python 3.11+.

```sh
cd backend
cp .env.example .env   # optional: add GEMINI_API_KEY for the explanation section
./run.sh               # http://localhost:8000
```

`run.sh` creates `.venv`, installs `requirements.txt` the first time (and again
whenever it changes), loads `.env` and starts uvicorn with auto-reload.

- http://localhost:8000/studio: the Field studio page
- http://localhost:8000: a sample report link for each case
- http://localhost:8000/docs: try every endpoint with custom inputs

## Field studio page

`/studio` serves `climate_lens/static/field-studio.html`, a self-contained page
(inline CSS and JS, no network calls) exported from `notebooks/Field_Studio.ipynb`.

The notebook is edited in
[Colab](https://colab.research.google.com/drive/1A0LzF05A8uSyTlaT8ecrI10--2yZG157),
which is the source of truth. The repo copy is synced from it:

- **Automatically:** the `Sync Field studio from Colab` GitHub Action checks every
  30 minutes and commits any change to the notebook and page. Run it right away
  from the repo's Actions tab with "Run workflow".
- **Locally:** pull the latest version and regenerate the page:

  ```sh
  .venv/bin/python scripts/export_studio.py --pull
  ```

The Colab link must stay shared as "Anyone with the link can view". Outputs are
cleared on sync so diffs show only code changes. Edit the notebook in Colab, not
in the repo: the next sync overwrites the repo copy.

The script reads the `DEMO_HTML` string from the last cell that defines it,
without running the notebook. The server picks up the new file immediately.

## API

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/health` | `{status, gemini_configured}` |
| GET | `/reports/options` | Cases with their stages, observations and default inputs |
| POST | `/reports` | Report as JSON |
| POST | `/reports/html` | Report as an HTML page (same body as `/reports`) |
| GET | `/reports/view?case=&stage=&observation=&explain=&question=` | HTML report for quick browser testing |

Only `case` is required (`satakunta-carrots`, `sakyla-peas`, `kantvik-rapeseed`).
Stage and observation default to the case's first ones, and calculator inputs
default to the notebook's values.

```sh
curl -X POST localhost:8000/reports -H 'content-type: application/json' -d '{
  "case": "sakyla-peas",
  "stage": "Flowering / young pods",
  "observation": "Pheromone traps detect moths",
  "impact": {"area": 120},
  "recovered": 50,
  "checks": {"monitoring": true},
  "explain": true,
  "question": "What should I inspect first?"
}'
```

Invalid selections or inputs return 422 with a message. With `explain: true`
the playbook and question are sent to Google's Gemini API. Without a key, the
report's `ai.status` is `unconfigured` and everything else still works.

Browser calls from the Svelte dev server (`http://localhost:5173`) are allowed.
Set `CORS_ORIGINS` in `.env` to allow other origins.

## Layout

- `climate_lens/data.py`: cases, playbook trees and plans (swap in the team's records here)
- `climate_lens/calculations.py`: decision logic and calculators, ported unchanged from the notebook
- `climate_lens/report.py`: assembles the report
- `climate_lens/gemini.py`: optional explanation
- `climate_lens/app.py`: FastAPI routes; `templates/` holds the HTML pages

## Tests

```sh
.venv/bin/python -m unittest discover tests
```
