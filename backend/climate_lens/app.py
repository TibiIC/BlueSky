"""HTTP API for Climate Lens report generation.

    GET  /                 index with a sample report link per case
    GET  /studio           Field studio page (exported from notebooks/Field_Studio.ipynb)
    GET  /reports/options  cases, stages, observations and default inputs
    POST /reports          report as JSON
    POST /reports/html     report as a printable HTML page
    GET  /reports/view     report as HTML from query parameters (for quick browser testing)
    GET  /docs             interactive API docs
"""

import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import gemini
from .data import CASE_LABELS
from .report import build_report, options

app = FastAPI(title="Climate Lens reports", version="0.1.0",
              description="Field decision reports from the FinlandIP DSS notebook. All figures are illustrative.")

# The Svelte frontend runs on :5173 in dev; add more origins via CORS_ORIGINS (comma-separated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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
    return {"status": "ok", "gemini_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip())}


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
