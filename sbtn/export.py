"""Export the SBTN review page from its notebook to site/index.html.

    python3 export.py [notebook]

Reads the APP string literal from the notebook (the notebook isn't executed), then
swaps the preloaded selection for the globe's: the embedded DATA is removed and the
page waits for the parcels the globe's Lens panel sends it (see GLOBE_BRIDGE).

SBTN_GLOBE_ORIGINS (comma-separated) lists the globe origins allowed to send a
selection. Default: the SvelteKit dev server.
"""

import ast
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "Climate_Lens_SBTN_Lite.ipynb"
OUTPUT = HERE / "site" / "index.html"
GLOBE_ORIGINS = [o.strip() for o in os.environ.get(
    "SBTN_GLOBE_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

DATA_START = "const DATA="
INIT = "({selected,name,matches,crossed,related,globeId}=DATA);"

# Replaces the notebook's init (from INIT to </script>). The globe opens this page and
# answers `sbtn:ready` with `sbtn:input`; see frontend/src/lib/lens/sbtn.ts.
GLOBE_BRIDGE = """
const GLOBE_ORIGINS=%s;
function load(d){
 if(!d||!Array.isArray(d.selected)||!d.selected.length||!Array.isArray(d.matches)||!Array.isArray(d.crossed)||!Array.isArray(d.related)){$('status').textContent='The globe sent a selection this page cannot read.';return}
 ({selected,name,matches,crossed,related,globeId}=d);review=fresh();step=0;
 const ids=new Set(matches.map(r=>r[1]));
 $('status').textContent='Globe selection · '+matches.length.toLocaleString('en')+' matched parcel'+(matches.length===1?'':'s')+' across '+ids.size+' catchment'+(ids.size===1?'':'s')+'.';
 evidence();draw();
}
window.addEventListener('message',e=>{
 if(e.source!==window.opener||!GLOBE_ORIGINS.includes(e.origin))return;
 if(e.data?.type==='sbtn:input')load(e.data.data);
 else if(e.data?.type==='sbtn:error')$('status').textContent='The globe could not prepare this selection: '+e.data.message;
});
if(window.opener){
 $('status').textContent='Waiting for the selection from the globe…';
 for(const o of GLOBE_ORIGINS)window.opener.postMessage({type:'sbtn:ready'},o);
}else{
 $('status').textContent='No selection yet. On the globe, circle an area with the drawing tool, then click “Open SBTN screening review” in the Climate Lens panel.';
}
</script></html>
"""


def app_html(notebook):
    html = None
    for cell in json.loads(notebook.read_text(encoding="utf-8"))["cells"]:
        if cell["cell_type"] != "code":
            continue
        for node in ast.parse("".join(cell["source"])).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "APP" for t in node.targets):
                html = ast.literal_eval(node.value)
    if html is None:
        raise SystemExit(f"No APP assignment found in {notebook}")
    return html


def connect_to_globe(html):
    """Remove the preloaded DATA and wait for the globe's selection instead."""
    start, init = html.find(DATA_START), html.find(INIT)
    if start < 0 or init < 0:
        raise SystemExit(f"The notebook page changed: expected `{DATA_START}…` and `{INIT}`. Update export.py.")
    _, end = json.JSONDecoder().raw_decode(html, start + len(DATA_START))
    if html[end] == ";":
        end += 1
    html = html[:start] + html[end:]
    html = html[:html.find(INIT)] + GLOBE_BRIDGE.strip("\n") % json.dumps(GLOBE_ORIGINS) + "\n"
    return html.replace("Preloaded globe selection · area-specific edition", "Selection from the globe")


if __name__ == "__main__":
    notebook = Path(sys.argv[1]) if len(sys.argv) > 1 else NOTEBOOK
    if not notebook.exists():
        raise SystemExit(f"{notebook} not found. Copy the notebook from Colab here, or pass its path.")
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(connect_to_globe(app_html(notebook)), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(HERE)} from {notebook.name}, waiting for selections from {', '.join(GLOBE_ORIGINS)}")
