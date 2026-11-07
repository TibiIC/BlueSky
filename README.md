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
