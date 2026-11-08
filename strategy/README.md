# Farm Missions (strategy proposals)

`Climate_Lens_Nutrient_Review.html` is the Farm Missions strategy page: missions, farm
shortlists, Räpi trial plans and an AI adviser draft per farm. It's a self-contained
HTML file (inline code and data).

The report backend serves it at http://localhost:8000/strategy (`backend/run.sh`). The
globe's **Scenario** tab links to it with **Open strategy proposals ↗**:

- the Scenario settings (year, warming, policies, farmer compliance, carbon price) and the
  selected area, if any, travel in the URL fragment (`#…`, never sent to a server);
- the page shows the scenario and limits itself to the selected area's parcels;
- "Generate recommendation" goes to `POST /strategy/recommend`, which uses Snowflake Cortex
  (`backend/.env`), so no API key is entered in the page.

The file on disk is never edited: `backend/climate_lens/strategy.py` patches it when serving.
To update the page, replace the file; if a patch no longer fits, `/strategy` returns an
error naming the part that changed.
