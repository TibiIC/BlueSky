# Live API / physics v2

Start `python3 server.py`; default loopback origin `http://127.0.0.1:8765`.

| Endpoint | Meaning |
| --- | --- |
| GET `/api/frame` | Regional snapshot, `schema: terra.frame.v1`, `engine_version: 2.0` |
| GET `/events` | Regional full snapshots via SSE, target 1 Hz |
| GET `/api/global-frame` | Coarse v1 global snapshot, `schema: terra.global-frame.v1` |
| GET `/global-events` | Global SSE snapshots |
| POST `/api/control` | Shared scenario controls, returns regional snapshot |
| GET `/api/health` | Service health/source mode |

Field arrays retain the v1 layout. Check engine_version for the changed regional physics and soil/snow ledger semantics; new v2 fields identify those changes. All timestamps are UTC. All arrays are finite or masked with JSON null. `ready:false` and `source.mode:waiting` mean no real forcing has arrived in strict mode: **do not render placeholder fields or integrate particles**. Every scalar field array is masked with null in that state. Synthetic mode is explicit; `open-meteo` denotes provider forecasts, not observations.

`source` includes `fetched_at`, `last_attempt_at`, `last_error`, `forecast_id`, `valid_start`, `valid_end`, sample count and interpolation method. `model_run_time` is null because retrieval time is not issuance time. Retained forecast data can be older than the most recent fetch attempt; check the actual timestamp/horizon. `published_at` is serialization time and `sim_time` is model time.

Regional grid: 25 columns × 29 rows, centers at 10–33°E and 54–71°N inclusive. Arrays are row-major, **south to north, west to east**. Index `j*nx+i`; lon=`west+i*(east-west)/(nx-1)`, lat=`south+j*(north-south)/(ny-1)`. For north-up textures, flip row order. The first/last regional raster cells are half-width to place centers at the stated bounds.

Regional `fields`:

- `u_ms`, `v_ms`: prescribed east/north forecast wind, m/s.
- `temp_c`: forecast air temperature, °C.
- `precip_mm_h`: raw precipitation water equivalent, mm/h. Multiply by regional `controls.rain_scale` for scenario display. Physics applies it internally.
- `et0_mm_h`: reference ET forcing, mm/h; actual soil ET is in the budget.
- `moisture_g_m3`: simulated effective-layer moisture, g/m³.
- `soil_mm`, `soil_fraction`: simulated 1 m soil storage and storage/capacity; ocean null.
- `snow_water_mm`: simulated snow water equivalent, mm; ocean null.

`initialization` records kind, time/source ID, soil depth, seeded land cell counts, capacity clipping and assumed snow density. `physics` describes numerical kernels/parameters. `water_budget_mean_land_mm` is the **area-weighted** last-step land ledger including snow. `atmosphere_budget_kg` reports mass before/after, boundary/nudging exchange, evaporation, precipitation removal, external precipitation supply and residual. See PHYSICS.md for equations.

Global: 36×17 centers at −180..170° longitude, −80..80° latitude; 10° spacing and periodic longitude. Display edges −180..180°, −85..85°; polar caps unmodeled. Shift the first center cell across the dateline. The global feed has no soil, snow, ET₀ output or v2 regional mass ledger. It retains the v1 transport/nudging model. Both clocks are published independently; check coverage instead of assuming exact synchronization.

SSE records use `event: frame`, an `id:` and a single complete JSON `data:` line followed by a blank line. TCP chunks need not align with SSE records. Reconnect to get the latest snapshot; no event history/replay is retained. The browser watchdog marks frames stale after four seconds, pauses particles and can recover through snapshot polling. `sequence` counts physics steps; reset can restart it. `revision` is the server update counter.

Controls:

```sh
curl -X POST http://127.0.0.1:8765/api/control \
  -H 'Content-Type: application/json' \
  -d '{"speed":600,"rain_scale":1,"capacity_mm":450,"paused":false}'
```

Speed 1–3600, rain multiplier 0–4, soil capacity 50–700 mm, paused/reset booleans. Unknown/invalid values reject atomically. Default is 1×. Reset reseeds at wall time from current API forcing and restores defaults. Capacity changes preserve saturation fraction; treat them as scenario interventions. Regional rainfall controls do not alter global forcing.

## BlueSky and later Unreal integration

BlueSky's allowlisted `/terra/*` server route proxies to Python on port 8765. `src/lib/weather/terra.ts` consumes these schemas, respects readiness/staleness, produces north-up field textures, and displays regional wind points. Geographic rectangle heights are visualization offsets, not model vertical levels. Terrain/buildings may occlude them; production terrain draping would replace this prototype approach.

`python3 stream_client.py --count 3` is a working SSE reference consumer, including WGS84 lon/lat/height→ECEF meters. It skips unready frames. For UE5, either consume SSE through a bridge or poll `/api/frame` at 1 Hz using the same schema. A WebSocket client cannot read SSE directly. Parse off the render thread, upload masked textures with the row orientation above, and use Cesium's georeference transform to map longitude/latitude/height to local Unreal coordinates. Transform east/north winds into the local tangent frame for Niagara. Preserve simulation time separately from frame interpolation; pause on stale data or the forecast horizon. No Unreal plugin/project has been implemented or tested here.

## Timeline switching

`POST /api/timeline` (or `/terra/api/timeline` in BlueSky):

```json
{"mode":"historical","start_date":"2026-10-24","end_date":"2026-10-24"}
```

Returns 202 with the active regional frame while loading in the background. Poll/subscribe to `frame.timeline.loading`, `error`, `mode`, `range` and `request_id`. The two grids switch together after successful acquisition. Choose 1–7 inclusive UTC dates from 1950 through yesterday. Old dates use ERA5 seamless; the recent reanalysis delay window uses forecast-API past data with a different explicit `source.forcing_kind`. Loading is never substituted with synthetic archive data.

`{"mode":"live"}` returns to latest live forcing, cancels any pending switch and resets state at current wall time only when returning from historical mode. Clicking the active live mode is idempotent. Scenario reset in historical mode restarts the selected period, not current time. In-flight old load completions cannot overwrite a newer live selection.

Regional frames contain `timeline.summary`, with hourly UTC series and area-weighted land precipitation/temperature/wind summaries for the selected period. `source.mode` is `open-meteo-history`; `forcing_kind` distinguishes `weather_reanalysis` from `recent_model_history`. `initialization.kind` similarly distinguishes archive/recent model seeding. Provider historical fields and replayed soil/moisture are different data products.

## Whole-world comparison and crop-weather diagnostics

`POST /api/comparison` with `{"date":"YYYY-MM-DD"}` loads the regional/global reference period asynchronously; GET returns the selected comparison against current wall-clock forecast forcing. It does not reset the physics clock. The `global` member has its own coarse grid, land mask, `live`, `historical` and `difference` fields; top-level fields retain Nordic detail. `summary` remains an area-weighted Nordic land summary.

Additional numeric arrays: `rain_day_mm`, `rain_day_coverage_h`, `frost_pct`, `heat_pct`, `wind_risk_pct`, `heavy_rain_pct`. A threshold flag is 0 or 100 per cell, not a probability. Regional mean percentages therefore describe flagged land area; their differences are percentage points. Daily-rain plots require coverage of all 24 hourly intervals; the coverage array in comparison differences is the minimum available coverage of the two source days, not subtraction. Thresholds are included in `screening_thresholds` and source agricultural metadata. No global soil/snow or actual farm-level damage is inferred.
