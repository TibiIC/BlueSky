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

Regional transport now prefers 850 hPa winds with explicit 10 m fallback. Surface wind screens still use 10 m winds. Moisture remains a near-surface humidity proxy in an effective 1 km layer, not a vertically resolved atmosphere. Land ET now includes a wilting-point floor and FAO-56 Ks × generic seasonal Kc × ET₀. Numerical diffusion and sparse weather sampling remain limitations. See the current upgrades below for denser bilinear forcing and a 2018 reanalysis benchmark. Independent observational validation and held-out yield calibration remain outstanding.

Derived data attribution: **Apetit Climate & Nature Navigator synthetic dataset, Since AI ry 2026 (CC BY 4.0)**. Licence and limitations are bundled in `frontend/static/data/apetit/`. The restricted original sample workbook is not redistributed. The three user-supplied patches were integrated and corrected for validation, seasonal loading races, filter-aware statistics and rendering depth.

Generated files are included, so normal startup needs no new dependencies. To regenerate from the original ZIP, install the optional build dependency in a virtual environment and run:

```sh
python3 -m venv .venv-apetit
.venv-apetit/bin/pip install duckdb
.venv-apetit/bin/python terra/apetit/build_farm_layers.py /path/to/APETIT_CLIMATE_NATURE_NAVIGATOR_2026.zip
```

## Measured soil biology pilot

Open **Measured soil biology · Finland + Sweden** in the sidebar. The independent cyan marker represents the single published Kungsängen meadow location. Select among 20 samples collected on **7 June 2016** to see derived fungal ASV richness, a natural-log Shannon index based on published sequence-read counts, sequencing depth and measured gravimetric water content. The archive publishes fungal records; it is not bacterial or whole-microbiome coverage. The Swedish dataset itself has no Finland coverage. No farm interpolation, current sensor readings or soil-health ranking is implied. The synthetic management proxy remains separately labeled.

Source: Rosling A, Eshghi Sahraei S, Furneaux B, Kluting K, Zakieh M (2026), *Kungsängen soil microbial communities*, version 1.9, Biology Section, Uppsala University / SBDI / GBIF, https://doi.org/10.15468/upxbwy, CC0 1.0. The derived file records the pinned archive URL, SHA-256, retrieval time, sampling protocol, dates and limitations. All 20 events share coordinates and have unspecified coordinate uncertainty. Sequence reads are not organism abundances; raw ASV richness is sequencing-depth dependent, and these derived metrics are not rarefied. Gravimetric g/g water content cannot be directly compared to the model's volumetric moisture.

Rebuild with standard-library Python:

```sh
python3 terra/biology/build_measured.py
```

Measured snapshots stay fixed while live weather animates. European LUCAS bacterial/fungal DNA data is a candidate for wider coverage, but its metadata requires ESDAC registration and is not included here.

## Finland biology, rain bands and decision evidence

The measured-biology panel now shows **Finland and Sweden together**: orange = Karstula (24 soil samples; 192 enzyme measurements, September 2021), cyan = Kungsängen (20 fungal DNA samples, June 2016). Karstula data are from Adamczyk et al. (2025), https://doi.org/10.5281/zenodo.13837158, CC BY 4.0. Soil-only rows are retained; root samples are excluded. Fungal biomass/necromass are biomarker-derived estimates in source-reported mg/g dry weight; they are not DNA diversity. Plot-level coordinates are unavailable, so one published study coordinate is used. Different methods cannot be merged into a country health ranking. Rebuild: `python3 terra/biology/build_finland.py`.

**Animated rain bands** displays forecast precipitation ≥0.1 mm/h using the evolving transported Nordic intensity proxy described below. It is not radar, nowcasting or meteorological front detection. Nordic forcing now samples **195 regular locations**, interpolated bilinearly to the existing 25×29 display/model grid; approximate forcing-point spacing is 100–135 km. This improves spatial support but does not make every display cell an independent measurement. Global forcing remains coarse. Both forecast fetches now occur hourly; SSE remains 1 Hz, with rain-texture animation at 5 Hz. Hourly precipitation intervals remain correctly accumulated. Typical background use is approximately 6,500 location/variable-weighted API calls/day, before interactive history requests; consult current Open-Meteo limits before sustained or commercial operation.

**Climate, validation & supply scenarios** contains public Open-Meteo CMIP6 HighResMIP projections for Säkylä and Bjuv from two models (MRI_AGCM3_2_S and EC_Earth3P_HR). It shows individual temperature and annual-rainfall changes for 2040–2049 versus 2000–2009. These ten-year windows are illustrative, not 30-year normals; the near-RCP8.5 model family is not a multi-SSP ensemble. Two-model spread does not cover all uncertainty.

The 2018 April–September benchmark evolves the FAO-56 land model hourly and compares daily end-point 0–1m water storage with ERA5-Land soil moisture, using ERA5/ERA5-Land seamless forcing and reference initialization. This is **not independent observational validation**. Zero initial snow, generic soil/crop assumptions and model discrepancy are exposed; no calibrated yield claim is made.

The supply screen combines those public environmental references with **synthetic** 2025 Apetit shipment-mode totals and 2026 crop prices. User-entered shortfall and avoided-shortfall assumptions drive a simple extra replacement-premium calculation. Annualized adaptation cost is also entered by the user. Rainfall is not automatically converted to lost tonnes. Route endpoints, actual supplier records, calibrated crop losses and financing effects are absent; no actual transport route or ROI is inferred. Export includes current inputs and source evidence.

Rebuild public decision evidence (network needed on first run; cache avoids repeated long-period API requests):

```sh
python3 terra/research/build_decision_data.py /path/to/APETIT_CLIMATE_NATURE_NAVIGATOR_2026.zip --cache /path/to/local-cache
```

## Animated weather and catchment routing

Selecting **Wind** or **Animated rain bands** starts the explicitly labeled **600× demo** (ten model minutes per real second) while motion is enabled. Pause/resume freezes the shared model clock and moving particles; **Return to live 1×** resets the live state to wall time. Wind tracers now render above weather surfaces and follow prescribed 10m forecast vectors across both global and Nordic grids. Wind itself is not a prognostic momentum simulation.

The Nordic rain display now uses `rain_pattern_mm_h`: a conservative finite-volume transported intensity proxy, driven by the transport-level winds (850 hPa when available) and relaxed toward forecast rain on a 30-minute timescale. The frontend blends successive model snapshots for smooth motion. This replaces decorative scrolling streaks. The tracer is not cloud microphysics, radar or meteorological front detection. Soil/snow and atmospheric water ledgers continue using forecast precipitation; the proxy does not invent rain input to the land model. Global rain remains hourly forecast forcing.

**Catchments & downstream rivers** adds real HydroBASINS level-5 polygons and HydroRIVERS geometry/topology for the Nordic model domain: 95 basin units and 10,471 larger reaches (Strahler order ≥4). Select a basin to highlight intersecting river reaches and inspect downstream IDs. The source provides IDs rather than river names. Geometry loads lazily when enabled. Lines, polygons and particles have elevated visualization offsets so they remain visible over weather layers; these are not physical water elevations.

Modeled runoff plus soil drainage enters area-weighted basin reservoirs, integrated with the land model. Each reservoir has an assumed 6-hour timescale and routes output via HydroBASINS `NEXT_DOWN`. Exact constant-inflow integration preserves the routing water balance. Published outflow is the **modeled regional contribution**, not calibrated full river discharge, flood stage or measured gauge flow. Routing starts with zero storage, external upstream inflow is absent, and domain-edge flow leaves the model. Lake/groundwater/infrastructure effects are not calibrated.

White river tracers follow oriented reach connections at `Q / assumed cross-section`, constrained to 0.1–3 m/s and displayed at the same clock speed. Q is HydroRIVERS modeled long-term average discharge (1971–2000), not live flow. Tracers reseed at retained-network exits. They illustrate direction and travel; basin storage/outflow is the separate conservative runoff response.

Sources: HydroBASINS/HydroRIVERS, WWF; Lehner & Grill (2013), https://doi.org/10.1002/hyp.9740. License, attribution and disclaimer are retained in `frontend/static/data/hydrology/HydroSHEDS_TechDoc_v1_4.pdf` (Appendix A). Geometry is generalized, and northern data above 60°N use a coarser underlying DEM; these are not farm-scale drainage boundaries. Coastal HydroBASINS units may aggregate multiple coastal drainages. The synthetic challenge catchment polygons are not substituted for these real boundaries.

Optional regeneration requires `pyshp` and `shapely` in the build environment, plus the official Europe level-5 basin and Europe river ZIPs (named `basins.zip` / `rivers.zip`): `python3 terra/hydrology/build_network.py /path/to/download-folder`. Normal runtime remains Python standard library plus the existing frontend dependencies.

Continuous weather surfaces (rain, wind speed, temperature and atmospheric moisture) use bilinear scalar interpolation on a denser display texture. Rain fades between 0.05 and 0.15 mm/h around the 0.1 mm/h display threshold; Nordic overlay edges feather into the coarse global view. Wind particles sample bilinear vector components, including periodic longitude at the dateline. These are rendering refinements, not additional weather measurements or a higher-resolution weather model. Categorical crop/risk masks and physical catchment boundaries retain their definitions.
