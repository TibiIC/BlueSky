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

## SBTN Step 1–2 screening report

`POST /sbtn/report` (JSON) and `POST /sbtn/report/html` (printable A4 page)
turn a globe selection into an SBTN Step 1–2 screening report. The SBTN review
page (`sbtn/`) opens it with **Generate report**, sending the selection and the
reviewer's answers.

`climate_lens/sbtn.py` computes every figure: Step 1a screens pressure categories
against the data, Step 1b quantifies pressures per catchment (runoff-risk
hectares, open ditches, organic soils, peat CO₂e, missing P tests), and Step 2
ranks catchments by pressure and by state of nature, then combines the ranks into
Priority / Secondary / Monitor tiers. Gemini writes the narrative sections from
those figures only; numbers in its text that aren't in the data are flagged in
the report. Without a key, or if the call fails, the report uses template text.

The report opens with a map of the area (`climate_lens/area_map.py`):
OpenStreetMap tiles fetched at report time, the drawn boundary, and each parcel
as a dot, red for runoff-risk parcels. Without internet it falls back to a plain
outline. `POST /sbtn/report/pdf` returns the report as a PDF (WeasyPrint; on
macOS it needs `brew install pango`).

This is an internal screening, not an SBTN validation submission.

## Farm Missions strategy page

`GET /strategy` serves `strategy/Climate_Lens_Nutrient_Review.html`, opened from the globe's
Scenario tab with the scenario and selected area in the URL fragment.
`POST /strategy/recommend` writes the per-farm adviser draft with the configured LLM.
See `strategy/README.md`.

## LLM providers

Report text comes from Snowflake Cortex when `SNOWFLAKE_ACCOUNT` and
`SNOWFLAKE_PAT` are set in `backend/.env`, otherwise from Gemini
(`climate_lens/llm.py`). `LLM_PROVIDER=snowflake|gemini` forces one, and
`GET /health` shows which is active.

**Snowflake Cortex** is called through its OpenAI-compatible Chat Completions
endpoint (`/api/v2/cortex/v1/chat/completions`) with a programmatic access
token. Default model `claude-sonnet-4-5`; override with `SNOWFLAKE_MODEL`.

### Gemini

Uses the official `google-genai` SDK (model `gemini-3.8-flash`, override with
`GEMINI_MODEL`). Create a key at https://aistudio.google.com/api-keys, put it in
`backend/.env` as `GEMINI_API_KEY=…`, and restart `./run.sh`.
`GET /health` reports `gemini_configured`.

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
