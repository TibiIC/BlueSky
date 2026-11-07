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

## Apetit demo filters and revised physics

The side panel includes Crops 2026, Soil class, Peat, Microbiome proxy, Timeline stress and Season replay. These overlay 14,213 **synthetic challenge parcel centroids**, with crop/region/peat filters and clickable cards. The microbiome toggle is only a management-based biodiversity-potential proxy; the package contains no microbial measurements. Soil/report mismatches are not proof of misreporting. A 29 t CO₂/ha/year peat scenario is illustrative.

The bundled April–September replays (2018, 2026, 2050 SSP5-8.5) use **synthetic daily weather from the challenge**, not ERA5 observations or a downloaded CMIP6 ensemble. They use generic spring-crop calendars, assumed root depths and soil capacities, and reuse the 2026 crop map. Play/pause/seek controls animate precomputed hourly-stepped FAO-56 results at an explicit days-per-second speed. Timeline stress instead samples the running regional API-forced model (live or historical); it does not infer farm-scale precision from the coarse weather grid. Crop/soil/peat attributes do not update each animation frame. Rotate Earth provides optional presentation motion.

Regional transport now prefers 850 hPa winds with explicit 10 m fallback. Surface wind screens still use 10 m winds. Moisture remains a near-surface humidity proxy in an effective 1 km layer, not a vertically resolved atmosphere. Land ET now includes a wilting-point floor and FAO-56 Ks × generic seasonal Kc × ET₀. Numerical diffusion and sparse weather sampling remain limitations. Denser/bilinear weather forcing, ERA5 validation of the 2018 drought, and held-out yield calibration are not implemented by these patches.

Derived data attribution: **Apetit Climate & Nature Navigator synthetic dataset, Since AI ry 2026 (CC BY 4.0)**. Licence and limitations are bundled in `frontend/static/data/apetit/`. The restricted original sample workbook is not redistributed. The three user-supplied patches were integrated and corrected for validation, seasonal loading races, filter-aware statistics and rendering depth.

Generated files are included, so normal startup needs no new dependencies. To regenerate from the original ZIP, install the optional build dependency in a virtual environment and run:

```sh
python3 -m venv .venv-apetit
.venv-apetit/bin/pip install duckdb
.venv-apetit/bin/python terra/apetit/build_farm_layers.py /path/to/APETIT_CLIMATE_NATURE_NAVIGATOR_2026.zip
```
