# Data curation

> Predict what every number should be, rank the gaps by how many tonnes of CO₂ they would move,
> and let a person check the top of the list.

**Method: [METHOD.md](METHOD.md)** (one page).

Apetit's raw records put the 2025 footprint at 18.8 million t. After curation it is 228,000 t:
grams typed as kg, kWh typed as MWh, supplier footprints per tonne instead of per kg.

1. **Predict** each number from an independent record: the shipment for a purchase, the same month
   in other years for a meter, the system's usual top-up for a refrigerant log.
2. **Compare** with a box plot of recorded ÷ predicted. A number beyond Tukey's far-out fences is
   flagged. Typos multiply by exact factors (×10, ×1,000, krona as euros); if undoing exactly one
   puts the number back inside the normal fences, it is fixed.
3. **Rank** everything else by tonnes of CO₂ at stake. A person decides in the app's **Dev** tab.
   Claude Haiku 5.5 adds one plain sentence per item; it explains, it never decides.

| Scored on the published 2023–2024 answers | Organisers' example | BlueSky |
|---|---|---|
| Footprint 2023 | 25.5 | **93.9** |
| Footprint 2024 | 23.2 | **78.4** |
| Errors found | 52.2 | **68.7** |

```sh
pip install pandas pyarrow pymongo anthropic
python3 -m quality.pipeline && python3 -m quality.publish_mongo
python3 -m unittest discover -s quality/tests -t .
```

| File | What it does |
|---|---|
| `gaps.py` | The method: expected values, gaps, typo test, options and tonnes at stake |
| `ai.py` | One plain sentence per item (Claude Haiku 5.5), cached |
| `impact.py` | Tonnes of CO₂ a change moves, with the package's emission factors |
| `pipeline.py` | Runs it, applies fixes and people's decisions to a copy, computes the footprint, scores it |
| `publish_mongo.py` | Saves the run and the corrected tables to MongoDB |
