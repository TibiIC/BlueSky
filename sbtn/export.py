"""Export the SBTN review page from its notebook to site/index.html.

    python3 export.py [notebook]

Reads the APP string literal from the notebook (the notebook isn't executed), then
swaps the preloaded selection for the globe's: the embedded DATA is removed and the
page waits for the parcels the globe's Lens panel sends it (see GLOBE_BRIDGE).

SBTN_GLOBE_ORIGINS (comma-separated) lists the globe origins allowed to send a
selection. Default: the SvelteKit dev server.

"Generate PDF report" posts the selection and the reviewer's answers to the
report backend (backend/, SBTN_REPORT_URL), which writes the SBTN Step 1–2
report with a hosted LLM and returns a PDF. It replaces the notebook's
line-by-line PDF. The page also swaps dropdowns for radio buttons and pre-fills
default answers.
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
REPORT_URL = os.environ.get("SBTN_REPORT_URL", "http://localhost:8000/sbtn/report/pdf")
MAP_URL = os.environ.get("SBTN_MAP_URL", "http://localhost:8000/sbtn/map")

DATA_START = "const DATA="
INIT = "({selected,name,matches,crossed,related,globeId}=DATA);"

# Replaces the notebook's init (from INIT to </script>). The globe opens this page and
# answers `sbtn:ready` with `sbtn:input`; see frontend/src/lib/lens/sbtn.ts.
GLOBE_BRIDGE = """
const GLOBE_ORIGINS=%s, REPORT_URL=%s, MAP_URL=%s;
function load(d){
 if(!d||!Array.isArray(d.selected)||!d.selected.length||!Array.isArray(d.matches)||!Array.isArray(d.crossed)||!Array.isArray(d.related)){$('status').textContent='The globe sent a selection this page cannot read.';return}
 ({selected,name,matches,crossed,related,globeId}=d);review=withDefaults();step=0;
 const ids=new Set(matches.map(r=>r[1]));
 $('status').textContent='Globe selection · '+matches.length.toLocaleString('en')+' matched parcel'+(matches.length===1?'':'s')+' across '+ids.size+' catchment'+(ids.size===1?'':'s')+'.';
 evidence();draw();cornerMap();
}
window.addEventListener('message',e=>{
 if(e.source!==window.opener||!GLOBE_ORIGINS.includes(e.origin))return;
 if(e.data?.type==='sbtn:input')load(e.data.data);
 else if(e.data?.type==='sbtn:error')$('status').textContent='The globe could not prepare this selection: '+e.data.message;
});
// Defaults so a reviewer can click Continue straight through, then adjust what they know.
const DEFAULTS={scope:'Needs verification',buffers:'Needs verification',habitat:'Needs verification',drainage:'Needs verification',
 nutrients:'Potentially material',water:'Insufficient evidence',habitats:'Insufficient evidence',comparison:'Comparison limited',
 attribution:'Not established',reviewer:'Climate Lens reviewer',period:'2027 planning season',decision:'Draft / follow-up needed'};
const withDefaults=()=>Object.assign(fresh(),DEFAULTS);
review=withDefaults();
// Radio buttons instead of dropdowns: every option is one click.
function control(k,title,opts){return '<fieldset class="radios"><legend>'+title+'</legend>'+opts.map(v=>'<label><input type="radio" name="'+k+'" data-key="'+k+'" value="'+esc(v)+'"'+(review[k]===v?' checked':'')+'> '+esc(v)+'</label>').join('')+'</fieldset>'}
document.head.insertAdjacentHTML('beforeend','<style>.radios{border:0;padding:0;margin:12px 0}.radios legend{padding:0;margin-bottom:6px}.radios label{display:flex;align-items:center;gap:8px;margin:4px 0;padding:8px 10px;border:1px solid #56746b;border-radius:8px;cursor:pointer}.radios label:has(input:checked){background:#213a38;border-color:#a8e2b0}.radios input{margin:0;accent-color:#a8e2b0}</style>');
// Replaces the notebook's PDF export: the backend computes the report, an LLM writes its text, and a PDF downloads.
async function download(){
 const btn=$('pdf'),status=$('review-status');
 if(!matches.length){status.textContent='No parcels from the globe yet. Open this page from the globe’s Climate Lens panel.';return}
 btn.disabled=true;btn.textContent='Generating report… (about 30 seconds)';
 try{
  const res=await fetch(REPORT_URL,{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({selection:{selected,name,matches,crossed,related,globeId},review,ai:true})});
  if(!res.ok)throw new Error((await res.json().catch(()=>({}))).detail||'HTTP '+res.status);
  const blob=await res.blob(),a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download=(res.headers.get('Content-Disposition')||'').match(/filename="([^"]+)"/)?.[1]||'SBTN-screening.pdf';
  document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),5000);
  status.textContent='Report downloaded: '+a.download;
 }catch(e){status.textContent='Could not generate the report: '+e.message+'. Is the backend running (backend/run.sh)?'}
 finally{btn.disabled=false;btn.textContent='Generate PDF report'}
}
// Corner thumbnail: swap the notebook's outline for a small real map (OSM tiles, boundary, parcel dots)
// drawn by the backend. Runs after the page has rendered and never throws; on any failure the outline stays.
function cornerMap(){
 setTimeout(async()=>{try{
  const res=await fetch(MAP_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({selected,matches})});
  const {map,attribution}=res.ok?await res.json():{};
  const svg=document.querySelector('#evidence svg');
  if(!map||!svg)return;
  const img=document.createElement('img');img.src=map;img.alt='Map of the drawn area with its parcels';
  img.title='Red: runoff-risk parcel. Blue: other parcel. '+attribution;
  img.style.cssText='display:block;width:100%%;border-radius:10px';
  svg.replaceWith(img);
 }catch(e){console.warn('Corner map unavailable:',e)}},0);
}
const drawNotebook=draw;
draw=function(){
 drawNotebook();
 $('step').querySelectorAll('input[type=radio]').forEach(x=>x.onchange=x.oninput);  // Safari fires change, not input
 const b=$('pdf');if(b)b.textContent='Generate PDF report';
};
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
    html = html[:html.find(INIT)] + GLOBE_BRIDGE.strip("\n") % (json.dumps(GLOBE_ORIGINS), json.dumps(REPORT_URL), json.dumps(MAP_URL)) + "\n"
    return html.replace("Preloaded globe selection · area-specific edition", "Selection from the globe")


if __name__ == "__main__":
    notebook = Path(sys.argv[1]) if len(sys.argv) > 1 else NOTEBOOK
    if not notebook.exists():
        raise SystemExit(f"{notebook} not found. Copy the notebook from Colab here, or pass its path.")
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(connect_to_globe(app_html(notebook)), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(HERE)} from {notebook.name}, waiting for selections from {', '.join(GLOBE_ORIGINS)}")
