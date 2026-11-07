"""SBTN Step 1–2 screening report for an area selected on the globe.

The numbers are computed here, deterministically, from the globe's selection
(frontend/src/lib/lens/sbtn.ts): Step 1a screens pressure categories against the
data available, Step 1b quantifies pressures per catchment, and Step 2 ranks
catchments by pressure and by state of nature and combines the two ranks, the
structure of SBTN's Step 2 method. A hosted LLM (Snowflake Cortex or Gemini, see
llm.py) then writes the narrative from those figures only; any figure it uses
that isn't in the data is flagged.

This is an internal screening, not an SBTN validation submission: validated
Steps 1–2 go through the Accountability Accelerator's templates.
"""

import json
import re
from datetime import datetime, timezone
from statistics import mean

from pydantic import BaseModel, Field

from . import area_map, llm

PLAN_YEAR = 2027  # planned crop year in the globe's data (lens/build_data.py)
NEAR_WATER_M = 100  # parcels this close to water without a buffer strip count as runoff risk
STATUS_SEVERITY = {"bad": 4, "poor": 3, "moderate": 2, "good": 1, "high": 0}
SOURCES = [
    ("SBTN Step 1: Assess overview", "https://sciencebasedtargetsnetwork.org/wp-content/uploads/2025/10/Step-1-Assess-Overview.pdf"),
    ("SBTN Technical Guidance for Steps 1 and 2", "https://sciencebasedtargetsnetwork.org/wp-content/uploads/2022/09/Technical-Guidance-for-Step-1-Assess-and-Step-2-Prioritize.pdf"),
    ("SBTN resources and templates", "https://sciencebasedtargetsnetwork.org/resources/"),
]


class Catchment(BaseModel):
    catchment_id: str
    region: str = ""
    receiving_water_type: str = ""
    ecological_status_class: str = ""
    catchment_area_km2: float | None = None
    p_sensitivity: float | None = None
    monitored: bool | None = None
    load: dict | None = None


class SelectionInput(BaseModel):
    """The globe's selection, as sent to the SBTN review page."""
    globeId: str = ""
    name: str = "Globe selection"
    selected: list = Field(default_factory=list)
    matches: list[list] = Field(default_factory=list)
    crossed: list[Catchment] = Field(default_factory=list)
    related: list[Catchment] = Field(default_factory=list)


class Parcel(BaseModel):
    id: str
    catchment: str
    ha: float
    buffer: bool
    drainage: str
    soil: str
    dist_water_m: float
    crop: str
    p_test: float | None = None
    peat_co2e: float = 0.0
    farm: str = ""
    contract: bool = False
    lon: float | None = None
    lat: float | None = None

    @classmethod
    def from_row(cls, r):
        keys = ["id", "catchment", "ha", "buffer", "drainage", "soil", "dist_water_m", "crop",
                "p_test", "peat_co2e", "farm", "contract", "lon", "lat"]
        return cls(**{k: v for k, v in zip(keys, r) if v is not None})


def rnd(x, nd=1):
    return round(float(x), nd)


def bbox(polygons):
    pts = [p for poly in polygons for p in (poly[0] if poly else [])]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [rnd(min(xs), 5), rnd(min(ys), 5), rnd(max(xs), 5), rnd(max(ys), 5)]


def outline_path(polygons, w=320, h=200, pad=10):
    """SVG path of the drawn area's outer rings, fitted to a w×h box (north up)."""
    rings = [poly[0] for poly in polygons if poly and poly[0]]
    box = bbox(polygons)
    if not rings or not box:
        return ""
    x0, y0, x1, y1 = box
    scale = min((w - 2 * pad) / max(x1 - x0, 1e-9), (h - 2 * pad) / max(y1 - y0, 1e-9))
    return " ".join("M" + " L".join(f"{pad + (x - x0) * scale:.1f} {h - pad - (y - y0) * scale:.1f}" for x, y in ring) + " Z"
                    for ring in rings)


def runoff_risk(p):
    return p.dist_water_m <= NEAR_WATER_M and not p.buffer


def per_catchment(parcels, catchments):
    """Step 1b: pressure indicators for each catchment the selected parcels drain to."""
    rows = []
    for c in catchments:
        ps = [p for p in parcels if p.catchment == c.catchment_id]
        if not ps:
            continue
        risk = [p for p in ps if runoff_risk(p)]
        load = c.load or {}
        rows.append(dict(
            catchment=c.catchment_id,
            region=c.region,
            water=c.receiving_water_type,
            status=c.ecological_status_class or "unknown",
            p_sensitivity=c.p_sensitivity,
            parcels=len(ps),
            farms=len({p.farm for p in ps if p.farm}),
            ha=rnd(sum(p.ha for p in ps)),
            contract_ha=rnd(sum(p.ha for p in ps if p.contract)),
            runoff_risk_parcels=len(risk),
            runoff_risk_ha=rnd(sum(p.ha for p in risk)),
            open_ditch_ha=rnd(sum(p.ha for p in ps if p.drainage == "open_ditch")),
            organic_ha=rnd(sum(p.ha for p in ps if p.soil == "organic")),
            peat_co2e=rnd(sum(p.peat_co2e for p in ps)),
            missing_p_tests=sum(1 for p in ps if p.p_test is None),
            outlet_load=dict(year=load.get("year"), p_kg=load.get("total_p_load_kg"), n_kg=load.get("total_n_load_kg"))
            if load else None,
        ))
    return rows


def rank(rows):
    """Step 2: rank by nutrient pressure and by state of nature, then combine the ranks."""
    def ranks(key):
        # Competition ranking: ties share a rank (1, 1, 3, …) instead of depending on input order.
        return {r["catchment"]: 1 + sum(key(o) > key(r) for o in rows) for r in rows}

    pressure = ranks(lambda r: (r["runoff_risk_ha"], r["open_ditch_ha"]))
    nature = ranks(lambda r: (STATUS_SEVERITY.get(r["status"], 0), r["p_sensitivity"] or 0))
    n = len(rows)
    out = []
    for r in rows:
        combined = (pressure[r["catchment"]] + nature[r["catchment"]]) / 2
        out.append(dict(catchment=r["catchment"], pressure_rank=pressure[r["catchment"]],
                        nature_rank=nature[r["catchment"]], combined=combined))
    out.sort(key=lambda x: (x["combined"], x["pressure_rank"], x["catchment"]))
    for i, x in enumerate(out):
        x["position"] = i + 1
        x["tier"] = "Priority" if i < max(1, round(n / 3)) else "Secondary" if i < max(2, round(2 * n / 3)) else "Monitor"
    return out


def screening(parcels, rows):
    """Step 1a: which pressure categories the selected activities point to, given this data."""
    ha = sum(p.ha for p in parcels)
    risk_ha = sum(r["runoff_risk_ha"] for r in rows)
    organic_ha = sum(r["organic_ha"] for r in rows)
    peat = sum(r["peat_co2e"] for r in rows)
    poor = [r["catchment"] for r in rows if STATUS_SEVERITY.get(r["status"], 0) >= 3]
    return [
        dict(pressure="Water pollution (nitrogen, phosphorus)",
             status="Potentially material" if risk_ha or poor else "Not indicated",
             evidence=f"{rnd(risk_ha)} ha within {NEAR_WATER_M} m of water without a buffer strip; "
                      f"{len(poor)} receiving water(s) in poor or bad status."),
        dict(pressure="Climate change (GHG from drained organic soils)",
             status="Potentially material" if organic_ha else "Not indicated",
             evidence=f"{rnd(organic_ha)} ha on organic soil, {rnd(peat)} t CO₂e/yr estimated."),
        dict(pressure="Land use (terrestrial ecosystem use)",
             status="Potentially material",
             evidence=f"{rnd(ha)} ha of cropland in the area. Conversion history is not in the data."),
        dict(pressure="Water use (withdrawal)",
             status="Not assessable with this data",
             evidence="No irrigation volumes for the selected parcels."),
        dict(pressure="Soil pollution, invasive species, other",
             status="Not assessable with this data",
             evidence="No parcel-level records for these pressures."),
    ]


def assess(selection: SelectionInput):
    """All figures in the report. Pure data: no model involved."""
    parcels = [Parcel.from_row(r) for r in selection.matches]
    linked = {c.catchment_id: c for c in [*selection.related, *selection.crossed]}
    rows = per_catchment(parcels, linked.values())
    ranking = rank(rows) if rows else []
    rows_by_id = {r["catchment"]: r for r in rows}
    crops = {}
    for p in parcels:
        crops[p.crop or "unknown"] = crops.get(p.crop or "unknown", 0) + p.ha
    return dict(
        selection=dict(name=selection.name, globe_id=selection.globeId, bbox_wgs84=bbox(selection.selected),
                       polygons=len(selection.selected)),
        totals=dict(parcels=len(parcels), farms=len({p.farm for p in parcels if p.farm}),
                    ha=rnd(sum(p.ha for p in parcels)), contract_ha=rnd(sum(p.ha for p in parcels if p.contract)),
                    catchments_crossed=len(selection.crossed), catchments_linked=len(rows)),
        plan_year=PLAN_YEAR,
        planned_crops_ha={k: rnd(v) for k, v in sorted(crops.items(), key=lambda kv: -kv[1])},
        screening=screening(parcels, rows),
        catchments=[rows_by_id[x["catchment"]] for x in ranking],
        ranking=ranking,
        crossed_without_parcels=sorted(c.catchment_id for c in selection.crossed if c.catchment_id not in rows_by_id),
        data_gaps=dict(
            missing_p_tests=sum(1 for p in parcels if p.p_test is None),
            catchments_without_outlet_record=sorted(r["catchment"] for r in rows if not r["outlet_load"]),
        ),
        method=dict(
            matching="Parcels whose centroid lies inside the drawn area.",
            runoff_risk=f"Parcels within {NEAR_WATER_M} m of water without a recorded buffer strip.",
            pressure_rank="Catchments ordered by runoff-risk hectares, then open-ditch hectares.",
            nature_rank="Catchments ordered by ecological status (bad > poor > moderate > good), then phosphorus sensitivity.",
            combined="Mean of the two ranks; top third Priority, middle third Secondary, rest Monitor.",
        ),
    )


NARRATIVE_INSTRUCTION = (
    "You write the narrative sections of an internal SBTN Step 1–2 screening report for a food company's "
    "agricultural sourcing area. Use only the figures in the supplied JSON and copy them exactly as given; "
    "do not compute new numbers, percentages or totals. Never invent thresholds, targets, legal requirements, "
    "species or causes. Outlet nutrient loads are catchment-wide: never attribute them to the company. "
    "Say plainly where data is missing. The data is synthetic challenge data, and this is a screening draft, "
    "not an SBTN validation submission. Write in plain, precise British English for a sustainability "
    "manager. No markdown."
)

NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string", "description": "3-4 sentences: what was screened, the main pressures, the priority catchments."},
        "materiality": {"type": "string", "description": "Step 1a: which pressure categories look material and why, 2-4 sentences."},
        "pressures": {"type": "string", "description": "Step 1b: what the per-catchment pressure figures show, 3-5 sentences."},
        "prioritisation": {"type": "string", "description": "Step 2: how catchments rank and why the priority ones lead, 3-5 sentences."},
        "data_gaps": {"type": "string", "description": "The evidence gaps that limit this screening, 2-3 sentences."},
        "next_steps": {"type": "array", "items": {"type": "string"}, "description": "3-5 concrete next steps toward SBTN Steps 1-2 validation."},
    },
    "required": ["executive_summary", "materiality", "pressures", "prioritisation", "data_gaps", "next_steps"],
}


def fallback_narrative(facts):
    """Plain template text, used when Gemini is off or fails."""
    t, top = facts["totals"], [r for r in facts["ranking"] if r["tier"] == "Priority"]
    return dict(
        executive_summary=f"The selected area contains {t['parcels']} parcels ({t['ha']} ha) from {t['farms']} farms "
                          f"draining to {t['catchments_linked']} catchments. Priority catchments: "
                          f"{', '.join(r['catchment'] for r in top) or 'none'}.",
        materiality="See the screening table: water pollution and organic-soil emissions are the pressures the data can evidence.",
        pressures="See the per-catchment table.",
        prioritisation="Catchments are ranked by runoff-risk hectares and by ecological status; see the ranking table.",
        data_gaps=f"{facts['data_gaps']['missing_p_tests']} parcels have no soil P test.",
        next_steps=["Verify the matched parcels against the sourcing register.",
                    "Confirm buffer strips and drainage in the field for the priority catchments.",
                    "Collect missing soil P tests."],
    )


def numbers_in(value):
    """Every number in a JSON-like value, as a set of normalised strings."""
    text = json.dumps(value, ensure_ascii=False)
    return {normalise(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def normalise(n):
    n = n.replace(",", "")
    return n[:-2] if n.endswith(".0") else n


def unverified_figures(narrative, facts):
    """Numbers Gemini wrote that don't appear in the facts (ignoring step numbers and small counts)."""
    known = numbers_in(facts) | {str(i) for i in range(0, 11)} | {"1a", "1b", "100"}
    found = numbers_in(narrative)
    return sorted(n for n in found if n not in known)


def narrative(facts, review, use_ai=True):
    if not use_ai:
        return dict(source="template", writer=None, note="AI text was not requested.", **fallback_narrative(facts))
    if llm.provider() is None:
        return dict(source="template", writer=None, note="No LLM is configured; showing template text.",
                    **fallback_narrative(facts))
    prompt = json.dumps({"report_figures": facts, "reviewer_assessment": review}, ensure_ascii=False)
    try:
        text = llm.generate(prompt, NARRATIVE_INSTRUCTION, schema=NARRATIVE_SCHEMA, max_output_tokens=2000)
    except llm.LLMUnavailable as error:
        return dict(source="template", writer=None, note=f"{error} Showing template text.", **fallback_narrative(facts))
    if not isinstance(text, dict):
        return dict(source="template", writer=None, note="The LLM reply wasn't an object. Showing template text.",
                    **fallback_narrative(facts))
    out = {k: text.get(k) or "" for k in NARRATIVE_SCHEMA["required"]}
    if not isinstance(out["next_steps"], list):
        out["next_steps"] = [str(out["next_steps"])]
    return dict(source="llm", writer=llm.label(), unverified=unverified_figures(out, facts), **out)


REVIEW_LABELS = {
    "scope": "Sourcing area", "buffers": "Buffers", "habitat": "Habitat presence", "drainage": "Drainage",
    "notes1": "Evidence, field checks and exceptions", "nutrients": "Nutrient runoff",
    "water": "Water availability or drainage", "habitats": "Habitat or biodiversity pressure",
    "comparison": "Cross-location comparison", "attribution": "Attribution to sourcing",
    "notes2": "Reasoning, priority locations and attribution method", "reviewer": "Reviewer",
    "period": "Reporting period", "decision": "Decision", "notes3": "Follow-up, owner and due date",
}


def build(selection: SelectionInput, review: dict | None = None, use_ai=True, with_map=True):
    review = {k: str(v)[:1500] for k, v in (review or {}).items() if k in REVIEW_LABELS and str(v).strip()}
    facts = assess(selection)
    parcels = [Parcel.from_row(r) for r in selection.matches]
    return dict(
        title="SBTN Step 1–2 screening",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="Reviewed for screening" if review.get("decision") == "Reviewed for screening" else "Draft screening",
        facts=facts,
        review=[dict(label=REVIEW_LABELS[k], value=v) for k, v in review.items()],
        narrative=narrative(facts, review, use_ai),
        outline=outline_path(selection.selected),
        map=area_map.render(selection.selected, parcels, runoff_risk=runoff_risk) if with_map else None,
        map_attribution=area_map.ATTRIBUTION,
        parcels=[p.model_dump() for p in parcels],
        sources=[dict(label=l, url=u) for l, u in SOURCES],
    )
