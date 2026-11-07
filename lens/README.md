# Climate Lens data

Turns the Apetit package (`APETIT_CLIMATE_NATURE_NAVIGATOR_2026`, team-only) into the small JSON files the
frontend's Climate Lens panel reads. The output is **not committed**: the package is for the team only, so
each machine rebuilds it.

```sh
pip install pandas pyarrow
python3 lens/build_data.py --package "/path/to/APETIT_CLIMATE_NATURE_NAVIGATOR_2026"
# or: export APETIT_PACKAGE=/path/to/...; python3 lens/build_data.py
```

It writes `frontend/static/data/lens/` (about 2 MB, ~5 s):

| File | Content |
|---|---|
| `parcels.json` | 14,213 parcels (columnar): soil map, slope, water distance, P test, buffer, 2025 crop, catchment, nearest climate cell, drained-peat t CO₂e |
| `farms.json` | Farm segment, organic share of contract area (soil map), 2025 survey soil answer, calculator footprints |
| `catchments.geojson` | Catchment polygons with status, P sensitivity, retention, contract hectares, latest monitored loads |
| `climate.json` | Per climate cell: growing-season indicators for 1991–2020, 2012–2026 and 2030s/40s/50s × SSP1-2.6/2-4.5/5-8.5 |
| `levers.json` | Parcel levers L08–L12, L24 and 2026 contract prices |
| `meta.json` | Package version, source paths and SHA-256 from `MANIFEST.json`, constants and method references |

## How the frontend uses it

1. Drawing an area posts it to `POST /api/selection`. The route adds `lens`: the report for contract parcels
   whose centroid lies in the area (`frontend/src/lib/lens/report.server.ts`).
2. The side panel (`LensPanel.svelte`) shows the report: area at a glance, conditions now, climate ahead by
   scenario and decade, peat and water, actions, evidence and review status.
3. "Conditions now" samples Andrew's TERRA feed (`/terra/api/frame`) at the area's centroid. It is empty, not
   invented, when TERRA isn't running.
4. The globe layer (`layer.ts`) draws catchments by water status and parcels by soil, and enlarges the
   parcels inside the selected area.

Numbers come from code and package files only. Every figure carries source keys that resolve to a file path
and hash in the Evidence section.
