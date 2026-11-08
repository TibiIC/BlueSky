"""HTTP API for Climate Lens report generation.

    GET  /                 index with a sample report link per case
    GET  /studio           Field studio page (exported from notebooks/Field_Studio.ipynb)
    GET  /reports/options  cases, stages, observations and default inputs
    POST /reports          report as JSON
    POST /reports/html     report as a printable HTML page
    GET  /reports/view     report as HTML from query parameters (for quick browser testing)
    POST /sbtn/report      SBTN Step 1–2 screening report for a globe selection, as JSON
    POST /sbtn/report/html the same as an HTML page (JSON body, or a form field `payload`)
    POST /sbtn/report/pdf  the same as a PDF download (what the SBTN page's Generate report uses)
    POST /sbtn/map         small map image of a selection (the SBTN page's corner thumbnail)
    GET  /strategy         Farm Missions strategy page, opened from the globe with its scenario
    POST /strategy/recommend  AI adviser draft for one farm (Snowflake Cortex)
    GET  /docs             interactive API docs
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import gemini, llm, sbtn, strategy
from .data import CASE_LABELS
from .report import build_report, options

app = FastAPI(title="Climate Lens reports", version="0.1.0",
              description="Field decision reports from the FinlandIP DSS notebook. All figures are illustrative.")

# Browser callers in dev: the Svelte frontend (:5173) and the SBTN review page (:8300).
# Add more origins via CORS_ORIGINS (comma-separated).
DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:8300,http://127.0.0.1:8300"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
STUDIO_PAGE = Path(__file__).parent / "static" / "field-studio.html"


class ImpactInputs(BaseModel):
    """Overrides for the cost & carbon scenario (peas, rapeseed). Omitted fields keep the case defaults."""
    area: float | None = Field(None, description="Contracted ha")
    yield_low: float | None = Field(None, description="Low yield t/ha")
    yield_high: float | None = Field(None, description="High yield t/ha")
    demand: float | None = Field(None, description="Required tonnes")
    premium: float | None = Field(None, description="Replacement premium €/t")
    action_cost: float | None = Field(None, description="Action cost €")
    baseline_co2: float | None = Field(None, description="Baseline t CO₂e")


class NettingInputs(BaseModel):
    """Preventive netting calculator (carrots, netting recommendation only)."""
    area: float | None = Field(None, description="Area covered (ha)")
    price: float | None = Field(None, description="Net purchase (€/ha)")
    seasons: int | None = Field(None, description="Reuse (seasons)")
    labor: float | None = Field(None, description="Seasonal labor (€/ha)")
    value: float | None = Field(None, description="Net crop value (€/t)")
    saved: float | None = Field(None, description="Assumed tonnes saved in total; unknown if omitted")


class GateChecks(BaseModel):
    monitoring: bool = Field(False, description="Current field monitoring recorded")
    threshold_met: bool = Field(False, description="Local action threshold confirmed and met")
    alternatives_insufficient: bool = Field(False, description="Feasible non-chemical options assessed and insufficient")


class ReportRequest(BaseModel):
    case: str = Field(description="One of: " + ", ".join(CASE_LABELS), examples=["satakunta-carrots"])
    stage: str | None = Field(None, description="Crop stage; defaults to the case's first stage")
    observation: str | None = Field(None, description="Field observation; defaults to the stage's first observation")
    impact: ImpactInputs | None = None
    recovered: float | None = Field(None, description="Assumed tonnes recovered by the action; unknown if omitted")
    added_co2: float | None = Field(None, description="Change in t CO₂e from the action; may be negative")
    netting: NettingInputs | None = None
    checks: GateChecks | None = None
    explain: bool = Field(False, description="Add a Gemini explanation (sends the playbook and question to Google)")
    question: str = Field("", max_length=500, examples=["What should I inspect first?"])
    model: str | None = Field(None, description=f"Gemini model ID; defaults to {gemini.DEFAULT_MODEL}")


def generate(req: ReportRequest):
    try:
        report = build_report(
            req.case, req.stage, req.observation,
            impact=req.impact.model_dump() if req.impact else None,
            recovered=req.recovered, added_co2=req.added_co2,
            netting=req.netting.model_dump() if req.netting else None,
            checks=req.checks.model_dump() if req.checks else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if req.explain:
        report["ai"] = dict(gemini.explain(report, req.question, req.model), question=req.question)
    return report


def render(request: Request, report):
    return templates.TemplateResponse(request, "report.html", {"r": report})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"cases": options()})


@app.get("/studio", response_class=FileResponse, include_in_schema=False)
def studio():
    return FileResponse(STUDIO_PAGE, media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok", "llm": llm.label(), "gemini_configured": gemini.configured(),
            "snowflake_configured": llm.snowflake_configured()}


@app.get("/reports/options")
def report_options():
    return options()


@app.post("/reports")
def create_report(req: ReportRequest):
    return generate(req)


@app.post("/reports/html", response_class=HTMLResponse)
def create_report_html(req: ReportRequest, request: Request):
    return render(request, generate(req))


@app.get("/reports/view", response_class=HTMLResponse)
def view_report(request: Request, case: str, stage: str | None = None, observation: str | None = None,
                explain: bool = False, question: Annotated[str, Query(max_length=500)] = ""):
    return render(request, generate(ReportRequest(case=case, stage=stage, observation=observation,
                                                  explain=explain, question=question)))


class SbtnReportRequest(BaseModel):
    selection: sbtn.SelectionInput
    review: dict[str, str] = Field(default_factory=dict, description="Reviewer answers from the SBTN review page")
    ai: bool = Field(True, description="Write the narrative with the configured LLM (sends the report figures to it)")


@app.post("/sbtn/report")
def sbtn_report(req: SbtnReportRequest):
    return sbtn.build(req.selection, req.review, req.ai)


@app.post("/sbtn/report/html", response_class=HTMLResponse)
async def sbtn_report_html(request: Request):
    """JSON body, or a form post with the JSON in `payload` (how the SBTN page opens it in a new tab)."""
    raw = await request.body()
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        raw = parse_qs(raw.decode()).get("payload", [""])[0]
    try:
        req = SbtnReportRequest.model_validate(json.loads(raw))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Expected {{selection, review, ai}}: {error}")
    report = await run_in_threadpool(sbtn.build, req.selection, req.review, req.ai)  # the LLM call blocks
    return templates.TemplateResponse(request, "sbtn_report.html", {"r": report})


def sbtn_pdf(report):
    """Render the report page to PDF (WeasyPrint uses the template's print styles)."""
    from weasyprint import HTML  # imported lazily: needs the pango system library
    html = templates.get_template("sbtn_report.html").render(r=report)
    return HTML(string=html).write_pdf()


@app.post("/sbtn/report/pdf")
async def sbtn_report_pdf(req: SbtnReportRequest):
    report = await run_in_threadpool(sbtn.build, req.selection, req.review, req.ai)
    try:
        pdf = await run_in_threadpool(sbtn_pdf, report)
    except OSError:
        raise HTTPException(status_code=500, detail="PDF rendering needs the pango library: brew install pango")
    stem = re.sub(r"[^A-Za-z0-9-]+", "-", req.selection.name.removesuffix(".geojson")).strip("-") or "selection"
    filename = f"SBTN-screening-{stem}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/sbtn/map")
async def sbtn_map(selection: sbtn.SelectionInput):
    """Thumbnail map (data URI) for the SBTN page: OSM tiles, boundary, parcel dots. map is null if tiles fail."""
    parcels = [sbtn.Parcel.from_row(r) for r in selection.matches]
    image = await run_in_threadpool(sbtn.area_map.render, selection.selected, parcels, 960, 400,
                                    sbtn.runoff_risk, 4, 16)
    return {"map": image, "attribution": sbtn.area_map.ATTRIBUTION}


@app.get("/strategy", response_class=HTMLResponse, include_in_schema=False)
def strategy_page():
    try:
        return HTMLResponse(strategy.page())
    except strategy.PageMissing as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:  # the page changed and a patch no longer applies
        raise HTTPException(status_code=500, detail=str(error))


class RecommendRequest(BaseModel):
    context: dict = Field(description="One farm's screening metrics, mission and the globe scenario, as the page sends them")


@app.post("/strategy/recommend")
async def strategy_recommend(req: RecommendRequest):
    if len(json.dumps(req.context)) > 30_000:
        raise HTTPException(status_code=413, detail="Context too large.")
    try:
        return await run_in_threadpool(strategy.recommend, req.context)
    except llm.LLMUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error))
