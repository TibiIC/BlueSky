# Validation — physics engine v2

Validated locally on macOS arm64 with Python 3.12/3.13 and a temporary official Node 24.22.2 runtime. No runtime binaries are bundled.

- **26 Python tests pass.** New v2 tests cover spherical finite-volume conservation with closed/open boundaries, CFL substepping and positivity, snow accumulation/melt, combined soil/snow water closure under extreme forcing, frozen-soil infiltration reduction, depth-integrated API initialization, depleted atmospheric reservoirs, strict live startup and first-real-fetch/reset behavior. Existing HTTP, controls, SSE, forecast intervals, wind wrapping, fallback, horizon and coarse-global tests remain passing. Exact output: `test-results.txt`.
- **Actual real API run:** `python3 validate_live.py --hours 6` fetched 25 regional Open-Meteo locations and initialized **500/500** regional land cells from forecast soil/snow state. **24 cells** were clipped to default soil capacity at initialization; this is recorded, not hidden. All 500 soil and snow states changed over the simulated six hours. Maximum area-weighted land budget residual was **2.6767e-15 mm**; maximum atmospheric relative residual **3.0475e-16**. See `live-physics-verification.json` for source hashes, timestamps, initialization details, cumulative fluxes and the final atmospheric ledger.
- **Live server:** actual `/api/frame` and BlueSky's `/terra/api/frame` returned engine version 2.0, ready=true and Open-Meteo source mode. Both regional/global frames passed through the bridge. `stream_client.py` consumed successive actual regional frames at approximately one-second cadence. Default simulation rate is now 1×, not accelerated demo time.
- **Viewer:** browser-confirmed API source labels, 500/500 land initialization, area-weighted snow/soil ledger and atmospheric relative residual. New soil/snow layers remain compatible with the BlueSky adapter. `physics-preview.png` shows the real-data dashboard.
- **Frontend:** Svelte/TypeScript check passed with 0 errors and 0 warnings; production build passed. Large Cesium client chunk and adapter-auto deployment notes are retained in `frontend-build-results.txt`. The standalone JS passed syntax checking and was exercised in-browser.

These are numerical conservation and integration checks, not validation against environmental observations. Open-Meteo inputs are forecasts. Snow density, soil capacity, degree-day melt, thermal relaxation, diffusivity and layer height are assumed. The land mask is schematic. No full atmospheric momentum solver, calibrated hydrology or terrain coupling is present. Global background physics remains v1. Optional keyed terrain/3D tiles and UE5 integration have not been tested.

Local preview services were stopped after QA. Follow README.md to restart; default mode requires actual API data, with synthetic modes explicitly selected.

## Overlay stability and historical-data update

- All 26 Python tests pass, including the historical-mode and mode-idempotence regressions. Tests cover date bounds, hourly summaries, async failure/cancellation, historical restart/live return, and protection against background live refresh overwriting archive state.
- Renderer regression: 600 streaming updates retain one geometry and one material, visibility toggles preserve them, and disposal is idempotent. The live renderer uses the persistent primitive path instead of Entity material rebatching.
- TypeScript/Svelte check and production build pass with the current viewer.
- Actual ERA5/ERA5-Land archive was loaded through the running HTTP timeline endpoint for 2026-10-24, with both global/regional sources and all 500 regional land cells initialized. The selected day had 1.842 mm area-weighted mean land precipitation; this is forcing data, not observed runoff. See historical-verification.json. A separate actual 2026-11-06 recent-history request also succeeded with usable soil data.
- Supplied Cesium ion imagery credentials returned HTTP 200, and the NLS orthophoto check returned HTTP 200/image/jpeg. No key values are in the report or downloadable archives.
- The demo is intentionally left running for the user's current viewing request; the earlier stop-after-QA note describes the prior packaged run.

## Global/Apetit filter update

- 38 Python tests pass, including crop thresholds, daily-interval completeness and 648-cell global/725-cell regional comparison coverage. TypeScript/Svelte check and build pass.
- Actual API comparison returned both grids, their land masks and all four crop-weather screens. Natural Earth land data is bundled, with source attribution. Crop thresholds are illustrative; no Apetit grower polygons or calibrated crop model were supplied.
- The parent GitHub URL was supplied after this prototype was created. GitHub authorization completed as AndrewBulata. Pull and push permissions were verified. Integration starts from actual parent main commit a23fc36 on branch codex/terra-apetit-weather. Credentials and API keys are excluded from Git.
