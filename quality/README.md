# Data quality

Apetit's records contain the usual typing slips: kWh typed where the column says MWh, grams where
it says kg, Swedish krona booked as euros, invoices posted twice. A few of them inflate the 2025
footprint about 75 times (Scope 3: 17.5 million t raw, 240,814 t after cleaning). This folder finds
those slips, fixes them where the evidence allows, and sends the rest to a person.

**Full explanation, in plain words first: [METHOD.md](METHOD.md).**

**How it works, in short:**

1. **Look for a second record of the same fact.** Every purchase also appears in the shipment
   records; certificates appear in the national registry; farm areas appear in the land register.
   When two records disagree, the independent one decides.
2. **Name the slip.** A difference of exactly 1,000× is a unit slip; 10× is a decimal point;
   11.4× is krona booked as euros. If no known slip explains the difference, we don't guess.
3. **Traffic light.** 🟢 Strong evidence: fixed. 🟡 Good evidence: fixed, a person confirms.
   🔴 Unclear: a person decides. Soil is the one exception: the footprint uses the soil map as the
   best estimate, and the farms where map and survey disagree most go to a person.
4. **Show the effect.** Each finding says how many tonnes of CO₂ it moves, the review list starts
   with the biggest uncertain ones, and the total comes with a range.
5. **AI helps the reviewer, never edits the data.** Claude Haiku 5.5 writes a short note per review
   item (what's wrong, its honest call, what to check). Code tests any suggestion it makes.

**Results on the organisers' published 2023–2024 answers:**

| | Their example solution | BlueSky |
|---|---|---|
| Finding the errors | 52.2 | **95.5** |
| Footprint 2023 | 25.5 | **99.3** |
| Footprint 2024 | 23.2 | **78.4** |

**Run it:**

```sh
pip install pandas pyarrow pymongo anthropic
python3 -m quality.pipeline                          # -> quality/out/ (findings, footprint, range, scores, 2025 submission)
python3 -m unittest discover -s quality/tests -t .   # tests for the checks and the evidence logic
python3 -m quality.verify_determinism                # the checks run twice give identical results
python3 -m quality.publish_mongo                     # -> MongoDB Atlas (MONGODB_URI in frontend/.env)
```

The AI notes need `ANTHROPIC_API_KEY` in `frontend/.env`; without it everything else runs the same
(`--no-ai` turns them off explicitly). Answers are cached, so re-runs cost nothing.

| File | What it does |
|---|---|
| `rules.py` | The checks: one per kind of slip, each recording the evidence it compared against |
| `evidence.py` | The trust ladder (A–G), the list of known slips, confidence |
| `assess.py` | Combines evidence per record, picks the best explanation, sets the traffic light |
| `impact.py` | How many tonnes of CO₂ each finding moves |
| `ai.py` | The reviewer's assistant (notes and tested suggestions) |
| `pipeline.py` | Runs everything and scores it against the published answers |
| `publish_mongo.py` | Saves the run and the cleaned tables to MongoDB |
