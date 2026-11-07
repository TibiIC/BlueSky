# TERRA — real-data physics engine, v2

Whole-Earth visualization with **a regional forecast-driven physics engine for Finland and Sweden** and a coarser global weather backdrop. This version replaces the regional visual tracer with conservative transport and couples land evapotranspiration, precipitation removal, snow and soil-water storage.

## Start with real data

Python 3.10+, no Python packages:

```sh
python3 server.py
```

Open **http://127.0.0.1:8765**. Default mode **waits for real Open-Meteo forecasts**, publishes `ready:false` with masked fields until they arrive, and starts at **1× wall time**. It does not silently run synthetic weather. The server fetches in the background; look for **API FORECAST**, the retrieval timestamp, initialization counts, and physics budget diagnostics.

- `python3 server.py --offline` explicitly runs synthetic forcing.
- `python3 server.py --allow-synthetic` permits a synthetic startup/fallback. First successful real data reseeds the regional model at wall time; metadata records the new initialization.
- `python3 server.py --port 8766` selects another port. BlueSky's bridge expects 8765 unless edited.
- Ctrl+C stops the server. State is in memory; restarting/resetting reinitializes from current available forcing.

Use 60×/600×/3600× for an accelerated demonstration. Acceleration advances forecast time, not the rate of API observations.

## What real data drives the engine?

Open-Meteo hourly forecasts are requested at **25 regional locations** and 24 global locations. Regional variables: temperature, humidity, wind speed/direction, precipitation, ET₀, three soil-moisture layers, surface soil temperature and snow depth. These are provider model products, **not weather-station or soil-sensor measurements**.

At initialization, volumetric soil moisture in 0–7, 7–28 and 28–100 cm layers is integrated into mm water over a 1 m soil profile. Initial snow water is inferred from API snow depth using an explicit assumed density of 200 kg/m³. Missing land initialization values retain marked assumptions. Source IDs, initialization time, seeded counts and capacity-clipped counts are published. Subsequent fetches update forcing without overwriting evolved soil/snow state; reset explicitly reseeds from the latest API data.

API fetch attempts run every 15 wall minutes. Hourly fields are interpolated in time; preceding-hour precipitation/ET₀ totals become interval rates. A successful retrieval can contain an unchanged forecast. Fetch time is not model issuance time. Forecast validity is enforced and the simulation holds at its horizon. Later failures retain the last valid forecast; the error stays visible. Strict mode holds rather than inventing initial data if the API is unavailable.

## What physics now runs?

The Nordic engine uses a 25×29 spherical grid (725 cells, approximately 35–68 km spacing):

- **Atmospheric moisture:** conservative finite-volume upwind advection, explicit diffusion and automatic CFL substeps. External forecast winds drive transport; forecast humidity supplies open boundaries and a separately accounted six-hour nudging source.
- **Land–atmosphere water exchange:** soil ET adds moisture to a chosen 1,000 m effective layer; prescribed precipitation removes available layer water. Precipitation exceeding the layer reservoir is labeled external/unresolved atmospheric supply instead of creating negative moisture.
- **Snow:** temperature-dependent rain/snow partition, snow storage and degree-day melt.
- **Soil:** infiltration limited by soil temperature, saturation runoff, ET moisture stress, and drainage. Soil and snow have an area-weighted water ledger; atmospheric mass has a separate ledger including boundary/source terms.

Default soil capacity is 450 mm over 1 m (assumed porosity 0.45), adjustable 50–700 mm. Changing capacity preserves saturation fraction and is a scenario intervention; it is not a natural flux. Rain multiplier 0–4 affects the regional model only.

Read **[PHYSICS.md](PHYSICS.md)** for equations, units, numerical checks and assumptions. Winds and air temperature remain forecast forcing. This is a reduced prescribed-wind engine; there is no prognostic momentum/pressure solver, convection, terrain-induced circulation, radiative energy balance or Richards-equation soil solver. Parameters are not calibrated. The land mask is schematic. Detailed imagery does not add meteorological resolution.

The 36×18 global grid retains the simpler v1 advection/nudging model with 10° spacing and no land physics. Global and Nordic models share the clock but are independently forced; they are not dynamically nested. Polar bands extend to 90° using sparse-sample interpolation; no polar circulation solver is claimed.

## Detailed Earth / BlueSky

Your original Downloads folder is untouched. An integrated copy is in `../frontend`. Keep Python running, then with Node 22.17+ or newer supported LTS and npm:

```sh
cd ../frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**. Use **Whole Earth** and **Nordics**, expand the TERRA panel with **+**, and choose moisture, precipitation, soil water, snow water, temperature or wind. Turn off the overlay to inspect imagery. Regional wind points animate with forecast velocity and the chosen simulation speed.

Default imagery uses the public Esri World Imagery MapServer with provider attribution, with bundled low-resolution Natural Earth beneath it. Actual resolution and availability vary. Existing optional Cesium ion/Google keys enable BlueSky's 3D tiles, and the optional NLS key enables Finnish orthophotos. No keys are bundled. Camera zoom is available worldwide; camera altitude is unrelated to weather grid resolution. No 3D terrain/buildings credentials were tested.

This is a local deliverable. Publishing requires an appropriate frontend server adapter and a deployed Python service/reverse proxy. Do not build while a preview is serving that same build directory. `npm run check`, `npm run build`, and `npm run preview` are available. The retained frontend README describes original BlueSky behavior; this root README supersedes its old zoom/imagery defaults.

## Verify and integrate

```sh
python3 -m unittest discover -s tests -v
python3 validate_live.py --hours 6
python3 stream_client.py --count 3
curl -N http://127.0.0.1:8765/events
```

`validate_live.py` actually fetches forecasts, seeds real state and advances the physics. It fails if no soil initialization is available or water budgets/positivity fail. The supplied **[live-physics-verification.json](live-physics-verification.json)** records a successful six-hour run using 25 actual API locations: 500/500 regional land cells seeded, all 500 soil/snow cells changed, land budget residual ≤2.7×10⁻¹⁵ mm and atmospheric relative residual ≤3.1×10⁻¹⁶. These are numerical balance checks, not validation against environmental measurements.

See **[API.md](API.md)** for the SSE/JSON contract and later UE5/Cesium integration, and **[VALIDATION.md](VALIDATION.md)** for local checks. Browser rendering targets native frames; physics scheduler targets 2 Hz and snapshots 1 Hz. The browser may recover through polling if a proxy buffers SSE. Slow machines can lag; catch-up is capped at two wall seconds per tick.

## Sources

[Open-Meteo forecast documentation](https://open-meteo.com/en/docs) defines variables/intervals; weather attribution: Open-Meteo, CC BY 4.0. Respect API quotas/terms; spatial interpolation is not the provider's native grid. [CesiumJS reference](https://cesium.com/learn/cesiumjs/ref-doc/) documents the renderer. Esri/Google/NLS credits remain in the viewer. Retained Natural Earth boundaries are public domain. BlueSky source was supplied by you.

## Live and historical replay

The 3D viewer now has **Live forecast** and **Historical replay** controls in the TERRA panel. Choose a UTC start/end date and click **Load period** (1–7 days at a time, 1950 through yesterday). Loading is asynchronous: the current data stays visible until both regional and global periods are ready. Failed requests leave the active simulation intact and show the error.

- Older periods use Open-Meteo's **ERA5/ERA5-Land reanalysis**. Recent dates use **past model data from the forecast API** while reanalysis catches up. The source notice identifies which product was used; neither is a direct station-observation series or an archive of forecasts exactly as issued.
- Replay seeds soil/snow at the selected period's start and runs the same reduced physics. Pause, change speed, or **Restart period**. It stops at the selected period's end. **Live forecast** returns to current forecast forcing and reinitializes at wall time; clicking it while already live does not reset the model.
- The panel shows hourly land-mean precipitation, total precipitation, the range of hourly mean air temperatures and peak hourly mean wind. These summarize the selected **weather forcing**, not measured catchment totals or modeled soil response. Replay physics outputs remain in the soil/snow/moisture layers.
- For consistent comparisons over older years, compare periods using the same reanalysis product. Recent model history and long-term reanalysis can differ systematically. Historical replay is conditional on the chosen soil/snow initialization and uncalibrated physical parameters.
- Up to three previously fetched periods are cached in memory. No CSV download is required.

The overlay renderer now keeps geometry/materials in place rather than changing Entity image properties every second. Canvas buffers update the material, and delayed/out-of-order feed/poll responses are ignored. This avoids the repeated geometry rebuilds that caused flashing. The renderer regression test runs with Node 24+: `node --test tests/overlay.test.mjs` in `../frontend`.

### Local imagery configuration

The active viewer reads `../frontend/.env`, not the original Downloads checkout's `.env`. Your supplied Cesium ion and NLS configuration has been loaded into that local file. It is ignored by Git and **excluded from downloadable project archives**, as are built assets that can contain public browser keys. To use your own keys after extracting a ZIP, create `.env` from `.env.example`, configure it, and rebuild/restart the frontend. Do not run a production build against the same output directory while preview is serving it.

References: [Open-Meteo historical weather](https://open-meteo.com/en/docs/historical-weather-api), [forecast API date ranges](https://open-meteo.com/en/docs).

## Global filters with Apetit-focused Nordic detail

Weather and live/historical difference filters now cover both the **36×18 global grid** and the **25×29 Nordic grid**, with the regional layer drawn above the coarse background. Global crop-weather screens use a bundled Natural Earth 1:110m cell-center land mask; polar bands are sparse-sample interpolation, not a polar circulation solver. The Nordic soil/snow model is still regional only.

The **Climate view** toggle means weather-layer visibility, as requested; it is not a long-term climatology mode. Global fields include temperature, hourly rain, full UTC-day rain, wind and the modeled moisture backdrop. Additional illustrative crop-weather screens flag air temperature ≤0°C, air temperature ≥28°C, mean 10 m wind ≥12 m/s and UTC-day precipitation ≥20 mm. These thresholds are transparent screening assumptions, not validated Apetit crop-damage, harvest or yield rules. Stage, cultivar, actual field boundaries and crop-specific tolerances have not been supplied.

For threshold screens, colored land cells meet the criterion; regional summaries give the area-weighted percentage flagged, and differences use percentage points. Full-day rain combines all 24 preceding-hour intervals for the selected UTC calendar day (including forecast future hours for today's forecast). Incomplete days are not rendered as full-day screens. Historical comparison uses matched UTC times for temperature/wind and matched UTC days for daily rain.

**Whole world** shows the global field. **Apetit focus** moves to Finland/Sweden. Säkylä and Bjuv markers identify approximate town centers related to [Apetit's cultivation and production overview](https://apetit.fi/en/sustainability/cultivation-and-experimental-work/), not actual farm plots or exact facilities. [Apetit strategy](https://apetit.fi/en/for-investors/apetit-as-an-investment/strategy-and-financial-objectives/) supplies the peas/vegetables/oilseed context; these references do not validate the assumed weather thresholds.

Land polygons: [Natural Earth vector land](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson), public domain. Focus-town coordinates were resolved with the Open-Meteo geocoding API. Rendering offsets of 12/13 km keep overlays above terrain and do not represent the atmospheric model's physical layer altitude.
