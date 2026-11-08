"""The Farm Missions strategy page (strategy/Climate_Lens_Nutrient_Review.html), served with the globe.

The page is a self-contained HTML file. At serve time it is patched, never edited on disk:

- The globe's "Open strategy proposals" link carries the Scenario settings and, optionally, the
  selected area in the URL fragment (#…, never sent to a server). The page reads them on load:
  the selection replaces the manual GeoJSON upload, and the scenario is shown and passed to the AI.
- "AI recommendation" calls POST /strategy/recommend here (Snowflake Cortex via llm.py) instead
  of Gemini from the browser, so no API key or model is entered in the page.

Each patch asserts its anchor text exists, so a new version of the page fails loudly instead of
silently losing the integration.
"""

import json
import os
from pathlib import Path

from . import llm

ROOT = Path(__file__).resolve().parents[2]
PAGE = Path(os.environ.get("STRATEGY_PAGE", ROOT / "strategy" / "Climate_Lens_Nutrient_Review.html"))

# The page's own instructions, kept server-side so the endpoint can't be used as a general LLM proxy.
INSTRUCTIONS = (
    "Write a concise adviser-review draft with four headings: Conclusion, Why this farm, Next steps, and "
    "Decision gate. Lead with verify, trial, hold, or consider limited rollout. Cite the specific supplied "
    "metrics and identify their limitations and the most important missing evidence. Give up to three actions "
    "with owners, an explicit trial comparator where relevant, and what would change the decision. Use only "
    "supplied contacts. Treat synthetic figures and model outputs as screening signals, not verified field "
    "evidence. Do not infer legal compliance, application rates, savings or causality. A submitted trial "
    "conclusion is user-entered evidence, not approval. Use plain text: no markdown, no #, no asterisks; "
    "write headings as plain lines. Do not calculate new figures (savings, emissions, percentages); quote only "
    "the supplied numbers. "
    "If a globeScenario is supplied (year, global warming, active policies, farmer compliance, prices), say "
    "briefly how that scenario changes the urgency or design of the actions; treat it as a planning "
    "assumption, not a forecast."
)

GEMINI_FETCH_START = "const response=await fetch('https://generativelanguage.googleapis.com/v1beta/models/'"
GEMINI_FETCH_END = "}catch{out.textContent='Gemini could not connect. Use the built-in roadmap.'}"

RECOMMEND_CALL = """const response=await fetch(RECOMMEND_URL,{method:'POST',signal:AbortSignal.timeout(120000),
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({context:{...context,globeScenario:GLOBE?.scenario??null}})});
  const body=await response.json().catch(()=>({}));
  if(!response.ok){out.textContent='AI recommendation unavailable ('+(body.detail||'HTTP '+response.status)+'). The built-in roadmap is available.';return}
  out.textContent='AI draft · '+body.writer+' · review with an adviser\\n\\n'+body.text;
 }catch{out.textContent='The recommendation service could not be reached (is backend/run.sh running?). The built-in roadmap is available.'}"""

# Runs before the page's first draw(): reads the globe's handoff from the URL fragment.
GLOBE_BRIDGE = """
// --- Climate Lens globe handoff (added when served by the backend) ---
const RECOMMEND_URL='/strategy/recommend';
const GLOBE=(()=>{try{return location.hash.length>1?JSON.parse(decodeURIComponent(location.hash.slice(1))):null}catch{return null}})();
(()=>{
 if(!GLOBE)return;
 const ok=p=>Array.isArray(p)&&p.length&&p.every(r=>Array.isArray(r)&&r.length>=4&&r.every(q=>Array.isArray(q)&&Number.isFinite(q[0])&&Number.isFinite(q[1])&&Math.abs(q[0])<=180&&Math.abs(q[1])<=90));
 if(Array.isArray(GLOBE.selection)&&GLOBE.selection.length&&GLOBE.selection.every(ok)){
  selection=GLOBE.selection;scopeName=String(GLOBE.name||'Globe selection').slice(0,120);showUploadRisk=true;
 }
 const s=GLOBE.scenario;
 if(s&&typeof s==='object'){
  const box=document.createElement('div');box.id='globeScenario';box.className='muted';
  const on=Array.isArray(s.policies)&&s.policies.length?s.policies.map(p=>esc(p.title)).join(' · '):'none (current policies)';
  box.innerHTML='<b>Scenario from the globe</b> · '+esc(s.year)+' · '+(s.warmingC!=null?esc(Number(s.warmingC).toFixed(2))+' °C global warming · ':'')+esc(s.pathway||'')
   +'<br>Policies on: '+on+(s.compliancePct!=null?'<br>Farmer compliance with regulations: '+esc(s.compliancePct)+' %':'')
   +(s.carbonPriceEurT!=null?' · EU carbon price €'+esc(Math.round(s.carbonPriceEurT))+'/t':'')
   +'<br><small>Passed to the AI recommendation as a planning assumption.</small>';
  $('scope').insertAdjacentElement('afterend',box);
 }
})();
"""

PATCHES = [
    # Gemini settings aren't needed: the backend holds the LLM credentials.
    ('<details id="aiSettings">', '<details id="aiSettings" hidden>'),
    ("const config=geminiConfig;", "const config={model:'snowflake',key:''};"),
    ("to Google without its farm ID or coordinates. Financial and trial results are optional. "
     "Use an API key from your Gemini project.",
     "to Snowflake Cortex (via the Climate Lens backend) without its farm ID or coordinates, together with "
     "the globe's scenario. Financial and trial results are optional."),
]

_cache = {"mtime": None, "html": None}


class PageMissing(Exception):
    pass


def patch(html):
    for old, new in PATCHES:
        if html.count(old) != 1:
            raise ValueError(f"Strategy page changed: expected exactly one {old[:50]!r}. Update strategy.py.")
        html = html.replace(old, new)
    start, end = html.find(GEMINI_FETCH_START), html.find(GEMINI_FETCH_END)
    if start < 0 or end < start:
        raise ValueError("Strategy page changed: Gemini request block not found. Update strategy.py.")
    html = html[:start] + RECOMMEND_CALL + html[end + len(GEMINI_FETCH_END):]
    final_draw = "\ndraw();\n</script>"
    if html.count(final_draw) != 1:
        raise ValueError("Strategy page changed: expected the script to end with draw(). Update strategy.py.")
    return html.replace(final_draw, "\n" + GLOBE_BRIDGE + "draw();\n</script>")


def page():
    """The patched page, re-patched whenever the file on disk changes."""
    if not PAGE.exists():
        raise PageMissing(f"Strategy page not found at {PAGE}. Put the Farm Missions HTML there.")
    mtime = PAGE.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["html"], _cache["mtime"] = patch(PAGE.read_text(encoding="utf-8")), mtime
    return _cache["html"]


def recommend(context):
    """Adviser-review draft for one farm. Raises llm.LLMUnavailable."""
    text = llm.generate(json.dumps(context, ensure_ascii=False), INSTRUCTIONS, max_output_tokens=1200, temperature=0.3)
    return {"text": text, "writer": llm.label()}
