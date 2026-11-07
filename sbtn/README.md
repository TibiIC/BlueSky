# Climate Lens · SBTN review (Lite)

Screens the parcels selected on the globe against SBTN steps 1–2 and exports the
review as a PDF. The page is exported from the `Climate_Lens_SBTN_Lite.ipynb`
Colab notebook and is self-contained (inline CSS and JS, no network calls).

## Run locally

```sh
cp ~/Downloads/Climate_Lens_SBTN_Lite.ipynb sbtn/   # once, or after each Colab change
sbtn/run.sh                                          # http://localhost:8300
```

`run.sh` re-exports `site/index.html` from the notebook on every start, then
serves it on `127.0.0.1` only. Use `PORT=9000 sbtn/run.sh` for another port, or
pass a notebook path: `sbtn/run.sh ~/Downloads/Climate_Lens_SBTN_Lite.ipynb`.

## Input from the globe

On the globe (`frontend/`, http://localhost:5173), circle an area with the
drawing tool, then click **Open SBTN screening review** in the Climate Lens
panel's Expert review section. The review opens in a new tab with that area's
parcels:

1. The panel posts the shape to `POST /api/sbtn`, which returns the drawn
   polygons, the parcels whose centroid lies inside, the catchments the area
   crosses and the catchments those parcels drain to (from the lens data).
2. The review page tells its opener `sbtn:ready` and receives `sbtn:input` back
   by `postMessage`. Reloading the review tab asks again.

`export.py` removes the notebook's preloaded example selection and adds that
receiver, so the page shows no parcels until the globe sends some. It accepts
selections only from the origins in `SBTN_GLOBE_ORIGINS` (default
`http://localhost:5173,http://127.0.0.1:5173`). If the review runs elsewhere,
set `PUBLIC_SBTN_URL` in `frontend/.env`.

## Not in git

The notebook embeds an example selection of parcel records from the team-only
Apetit package, so it's git-ignored. `site/` is generated. Only these scripts
are committed.
