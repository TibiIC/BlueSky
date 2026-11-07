# How BlueSky curates Apetit's data

> **Predict what every number should be, rank the gaps by how many tonnes of CO₂ they would move,
> and let a person check the top of the list.**

## Why it matters

Apetit's records contain everyday typing slips. A handful of them make the 2025 footprint
meaningless:

| 2025 | Raw data | After curation | Main cause |
|---|---|---|---|
| Scope 1 | 132,163 t | **4,414 t** | 85,150 *grams* of refrigerant typed as kg |
| Scope 2 (market) | 1,117,417 t | **61 t** | kWh typed into the MWh column; certificates not matched to the registry |
| Scope 3 | 17,535,696 t | **223,911 t** | three suppliers gave their footprint per tonne in a per-kg field |

The damage is concentrated: in 2025 the 10 biggest errors account for 99.9 % of all the error.
So the method is built to find the big ones first.

## The method in three steps

### 1. Predict

Every number that drives the footprint gets an **expected value** from an independent or typical
source:

| Record | Expected value comes from |
|---|---|
| Purchase quantities | the tonnes the **shipment record** says the truck carried for the same purchase |
| Purchases with no shipment | the amount paid ÷ the material's typical price |
| Amounts paid for goods | the kilos × the material's typical price |
| Services and capex invoices | the supplier's typical invoice |
| Energy meters | the same month in the other years |
| Refrigerant top-ups | the system's usual top-up |
| Fuel deliveries, waste notes | the usual delivery or note for that carrier or stream |
| Supplier footprints (kg CO₂e/kg) | the supplier's previous year, else the library factor |
| Commuting distances | the site's typical one-way distance |
| Farm yields and fertiliser | the crop's median that year |
| Gas code, certificates, soil | the system's usual gas, the national registry, the soil map |

### 2. Compare

We compare recorded and expected **on a log scale**: gap = log₁₀(recorded ÷ expected). This is a
regression of log(recorded) on log(expected) with slope 1. Clean records sit on the diagonal, and
the spread around it is the series' noise. We measure it robustly (1.4826 × the median absolute
deviation), so the errors themselves can't widen it.

A number is **flagged** when it is more than 4 noise-widths from the line *and* at least 2.5× off.

On a log scale typos are easy to recognise, because they land on **exact lines** parallel to the
diagonal:

| Typo | Gap | Typical cause |
|---|---|---|
| ×1,000 or ÷1,000 | ±3.00 | grams as kg, kWh as MWh, litres as m³, metres as km, per tonne as per kg |
| ×10, ×100 | ±1.00, ±2.00 | a misplaced decimal point |
| krona as euros | +1.06 | a Swedish invoice booked in euros (×11.4) |

Each kind of record is tested only for the typos that really happen to it: grams/kg for
refrigerants, kWh/MWh for meters, a misplaced decimal point for farm answers, krona for invoices.

### 3. Decide, and rank by tonnes at stake

- **Fixed automatically:** exactly one typo explains the gap, and after undoing it the value sits
  within the normal spread. Example: the meter reading of 1,708,632 "MWh" against a usual 1,785
  is fixed to 1,708.6.
- **For a person:** everything else. Our best guess goes into the numbers until they decide: the
  best-fitting typo, the registry, the soil map, or, for meters, the same month in other years.
  A gap no typo explains (an invoice that is simply large) keeps its recorded value.
- **Tonnes at stake:** for every option, how much the footprint would move, with the package's own
  emission factors. The list is sorted by it.

**One sentence from an AI.** For each item, Claude Haiku 5.5 writes one plain sentence: what went
wrong and what it was fixed to, or what to check. It is given the facts the method computed, including
the known cause for that kind of record (for example "kWh typed into the MWh column"), so it doesn't
guess. It explains; it never changes a number or decides a status. Answers are cached, so re-runs cost
nothing, and without an `ANTHROPIC_API_KEY` everything else runs the same.

In the app's **Dev** tab a person sees the scatter plot, the 2025 footprint, and the list. For each
number they pick an option ("divide by 1,000", "use the registry", "keep the recorded value"…),
signed with their name. Decisions are saved in MongoDB, and the next pipeline run applies them. Raw
data is never changed: every fix is applied to a copy.

## A worked example

Purchase document 4500006858 (2025) records 143,784 kg of pizza cheese for €647,579. Price alone
says something is wrong, because it is about 9× the usual price per kg. A price-only check would
multiply the kilos by 10.

The shipment record says the truck carried **143.784 t**, so the kilos are right. The amount is
off instead, by about the krona rate: an invoice in krona booked as euros. Goods emissions come from
kilos, so the footprint doesn't change. The organisers' answers label the 2023–2024 cases exactly
this way.

## How well it works

Scored on the organisers' published 2023–2024 answers:

| | Organisers' example | BlueSky |
|---|---|---|
| Footprint 2023 | 25.5 | **93.9** |
| Footprint 2024 | 23.2 | **78.4** |
| Errors found | 52.2 | **68.7** |

- **Automatic fixes:** 75 of 75 in 2023–2024 are real errors in the answers.
- **Items for a person:** 40 of 55 are real errors. The others are mostly soil (the map is right
  about 88 % of the time) and large invoices that really are large. That's why a person decides
  them.
- **What we deliberately skip:** errors that are not wrong numbers: duplicate postings, wrong
  material codes, mislabelled commuting modes, stale supplier footprints. They count for the
  error-finding score, and most barely move the footprint. The exception is wrong material codes:
  6 lines in 2025, about 1,600 t (the cheese line above is one: its text says pizza cheese, its
  code points to a low-emission material). This is the trade we chose for simplicity.

## Commands

All commands run from the repository root (`BlueSky/`) unless noted.

**One-time setup**

```sh
pip install pandas pyarrow pymongo anthropic      # Python 3.11+
cd frontend && npm install && cd ..                # the app (Node 22: nvm use 22)
```

`frontend/.env` holds the keys (never committed):

```sh
MONGODB_URI=mongodb+srv://...      # MongoDB Atlas
MONGODB_DB=bluesky
ANTHROPIC_API_KEY=sk-ant-...       # optional: the one-sentence explanations
```

The Apetit package is read from `~/Downloads/Apetit_SinceAI2026 _1_/Apetit_SinceAI2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026`.
Elsewhere, pass `--package PATH` or set `APETIT_PACKAGE`.

**Refresh the data (run this after people have made decisions in the Dev tab)**

```sh
python3 -m quality.pipeline          # predict, compare, fix, explain, footprint, scores -> quality/out/  (~1 min)
python3 -m quality.publish_mongo     # send the run to MongoDB; the Dev tab shows it on reload
```

**Start the app**

```sh
cd frontend && npm run dev -- --port 5199     # then open http://127.0.0.1:5199 and pick the Dev tab
```

**Check it**

```sh
python3 -m unittest discover -s quality/tests -t .    # tests for the method
cd frontend && npm run check                           # type-check the app
```

**Options for `quality.pipeline`**

| Option | Effect |
|---|---|
| `--no-decisions` | ignore the choices saved in the Dev tab (see what the method alone does) |
| `--no-ai` | skip the one-sentence explanations (no API calls) |
| `--ai-limit N` | explain only the N items with the most tonnes at stake (default 250) |
| `--package PATH` | where the Apetit package is |
| `--out DIR` | where results go (default `quality/out/`) |

**What `quality/out/` contains:** `A1_issues_submission.csv` and `A2_inventory_2025_submission.csv`
(the hackathon deliverables), `summary.json` (scores, totals, noise per series), `items.json` (every
flagged number), `points.json` (the scatter plot), `inventory.json`, and `processed/*.parquet` (the
corrected tables).

MongoDB collections: `dev_runs` (method, noise per series, scores, totals, scatter points),
`dev_items` (every flagged number with its options and tonnes), `dev_decisions` (people's choices),
`inventory`, and the corrected tables `proc_*`.

## Limitations

- Each prediction is only as good as its source. A typical invoice or top-up is a loose prediction,
  so only large gaps are flagged there.
- Tonnes at stake are first-order (change × emission factor). The footprint itself always comes from
  the organisers' reference calculator.
- The soil map is about 88 % accurate, so soil is always a person's call. The footprint uses the map
  until they decide.
- Farms that didn't answer the survey get the respondents' production-weighted average. That's the
  main reason 2024 scores lower than 2023.
