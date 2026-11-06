# BlueSky frontend: Nordic globe

Interactive 3D globe (SvelteKit + TypeScript + CesiumJS) focused on Finland and Sweden, with a red drawing tool for selecting areas.
Each finished shape is sent to `POST /api/selection`, which validates it and returns its area, centroid and country overlap.

```sh
cd frontend
cp .env.example .env   # optional: add keys, see below
npm install
npm run dev            # http://localhost:5173
```

Requires Node 22.17 or later.

## Keys and rendering tiers

All keys are optional. The globe degrades gracefully depending on which keys are set in `frontend/.env`:

| Key | Unlocks | Without it |
| --- | --- | --- |
| `PUBLIC_CESIUM_ION_TOKEN` | Global satellite imagery (ion / Bing aerial), and Google Photorealistic 3D Tiles via ion | Keyless low-res Natural Earth II imagery (console warning), no 3D cities unless a Google key is set |
| `PUBLIC_GOOGLE_MAPS_API_KEY` | Google Photorealistic 3D Tiles fetched directly from Google (your own quota) | 3D tiles come via Cesium ion, if a token is set |
| `PUBLIC_NLS_API_KEY` | National Land Survey of Finland orthophoto, clipped to Finland | Finland uses the world imagery |

Restart `npm run dev` after editing `.env`. The top-right corner lists which layers are active.

### Cesium ion token (recommended)

1. Sign up for free at <https://ion.cesium.com/signup>.
2. Open **Access Tokens** (<https://ion.cesium.com/tokens>). Copy the **Default** token, or click **Create token** with the default `assets:read` scope.
3. Optional: under **Allowed URLs** add `http://localhost:5173` and your deployment URL.
4. If 3D cities fail to load, open **Asset Depot**, search for "Google Photorealistic 3D Tiles", and click **Add to my assets**.

### Google Map Tiles API key (optional)

1. In the Google Cloud Console (<https://console.cloud.google.com/>), create a project and attach a billing account.
2. Enable the **Map Tiles API** (APIs & Services → Library).
3. Go to APIs & Services → Credentials → **Create credentials → API key**.
4. Restrict the key to the **Map Tiles API**, with HTTP referrers `http://localhost:5173/*` and your deployment URL.

### NLS Finland API key (optional)

1. Register at the NLS My Account service: <https://omatili.maanmittauslaitos.fi/user/new/avoimet-rajapintapalvelut?lang=en>.
2. Log in at <https://omatili.maanmittauslaitos.fi/> and create a new API key.

The open WMTS is meant for light use and answers bursts with HTTP 503.
The app limits it to 4 parallel requests, requests it only inside Finland, and requests it only once zoomed in.
The orthophoto is draped on the plain globe, so it shows when **3D cities** is off.

## Using the globe

- **Mouse:** left-drag rotates, scroll or pinch zooms, and right-drag or Ctrl-drag tilts.
- **Zoom limits:** inside lon 10.5–31.6° E, lat 55.0–70.1° N you can zoom to about 300 m. Elsewhere the camera stays above about 1,000 km, ramping smoothly over a 2.5° band around the box.
- **3D cities on/off** switches Google 3D tiles. While the tiles are on, the plain globe is hidden, as Cesium recommends for Google tiles.

### Drawing

| Mode | How |
| --- | --- |
| Navigate | Default. Click a red shape to select it. |
| Freehand | Press and drag a lasso, then release to close it. Hold **Shift** in any mode to draw freehand temporarily. |
| Polygon | Click to place points. Close with a double-click, **Enter**, or a click on the first point. **Esc** cancels. |

**Delete** or **Backspace** removes the selected shape, or the last point while you are drawing a polygon.
**Undo** reverts the last add, delete or clear.
**Export GeoJSON** downloads the FeatureCollection.

Shapes are 2D: points are picked on the 3D tiles (`scene.pickPosition`) or the ellipsoid, then stored as lon/lat with no height.
Freehand strokes are sampled every 4 px and simplified with Douglas–Peucker at 1.5 px tolerance.
Before a shape is stored, the app closes it, removes self-intersections (keeping the largest loop) and orients it counter-clockwise (RFC 7946).
Shapes under 100 m² are dropped.

## API

`POST /api/selection` accepts a GeoJSON `Feature` or `FeatureCollection` of `Polygon`s and validates it with zod (closed rings, lon in [-180, 180], lat in [-90, 90]).

```sh
curl -X POST localhost:5173/api/selection -H 'content-type: application/json' -d \
  '{"type":"Feature","properties":{"id":"demo"},"geometry":{"type":"Polygon","coordinates":[[[24.5,60.1],[25.2,60.1],[25.2,60.4],[24.5,60.4],[24.5,60.1]]]}}'
# {"id":"demo","bbox":[24.5,60.1,25.2,60.4],"areaKm2":1288.431,"centroid":{"lon":24.85,"lat":60.25},"countries":["Finland"]}
```

`countries` lists whichever of Finland and Sweden the shape intersects, using Natural Earth 1:50m outlines; Finland includes Åland.
A FeatureCollection returns aggregate values plus a per-feature `features` array.
Invalid input returns HTTP 400 with `issues`.

## Code map

```
src/env.ts                  public env vars (SvelteKit 3 defineEnvVars → $app/env/public)
src/routes/+page.svelte     layout: globe stage + collapsible right panel slot (toggle with "]" in dev)
src/routes/+page.ts         ssr = false (Cesium is browser-only, loaded in onMount)
src/routes/api/selection/   POST endpoint
src/lib/globe/              viewer setup, imagery tiers, zoom clamp, camera controls, city labels, borders
src/lib/drawing/            drawing tool, shape store (GeoJSON FeatureCollection), rendering, geometry, API client
src/lib/ui/                 Toolbar, Hud, TilesToggle, SidePanel
src/lib/geo/                regions, country polygons, Turf helpers and request schema (shared client/server)
static/data/borders.geojson Natural Earth 1:50m land boundaries (public domain)
```

A future side panel can subscribe to `shapes`, `selectedShape` and `analyses` from `#lib/drawing/store.ts`, and render inside `<SidePanel>` in `+page.svelte`.

## Attribution

Cesium, Google and NLS credits are shown in the bottom-right corner, as their terms require.
Borders come from [Natural Earth](https://www.naturalearthdata.com/), which is public domain.
