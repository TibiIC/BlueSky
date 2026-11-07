# BlueSky / TERRA

Whole-Earth Cesium viewer with API-driven weather, conservative Nordic moisture transport, snow/soil water balance, historical replay and global crop-weather screening for an Apetit-focused prototype.

## Run

Python 3.10+ and Node 22.17+ (or a supported newer LTS) are required.

Terminal 1, from the repository root:

```sh
python3 terra/server.py
```

Terminal 2:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. Optional imagery keys go in frontend/.env; use .env.example. Never commit that file.

The physics service requires real Open-Meteo data by default. Use --offline explicitly for synthetic forcing. All weather layers and live/historical differences cover a coarse global grid, with finer Nordic detail. Soil/snow physics remains regional. Crop thresholds and approximate Apetit-region markers are illustrative rather than calibrated farm/yield predictions.

## Validate

```sh
cd terra
python3 -m unittest discover -s tests -v
```

In frontend: npm run check and npm run build. With Node 24+: node --test tests/*.test.mjs.

See [physics and data scope](terra/README.md), [equations](terra/PHYSICS.md), [API](terra/API.md), and the retained [original frontend guide](frontend/README.md).

## Explore regional evolution

The collapsible right sidebar leaves the globe unobstructed. Weather visibility and field selection apply to both global and Nordic grids. Global fields cover all longitudes pole to pole, on 18 latitude bands centered at 85°S..85°N. Polar bands are sparse-sample interpolation, not a polar circulation model. Soil and snow are Nordic-only. Open the timeline section for historical replay or the comparison section for matched-hour live/past weather.

Open **Regional evolution & adaptation** to run baseline and hypothetical stress conditions from identical API-initialized stores. Set a local temperature offset, rainfall multiplier, independent evaporation-demand multiplier, and duration (up to 168 hours, limited by the available forcing period). This uses the existing snow/infiltration/soil/evaporation/runoff/drainage equations in 15-minute steps, with hourly summaries for Finland, Sweden and the Nordic domain. It leaves the live simulator untouched. Map the final scenario soil state or export the complete JSON results, assumptions and source metadata. Changing field or timeline exits the frozen scenario map.

These short-period sensitivity experiments are not long-term climate projections. Temperature does not automatically recompute atmospheric circulation or reference evaporation; evaporation demand is an explicit independent input. The country masks, capacity and dry-area threshold are approximate and uncalibrated. Policy and supply-chain decisions require supplier/farm boundaries, crops and growth stages, calibrated impact models, historical validation and regional climate ensembles with uncertainty.
