"""Assemble a Climate Lens report: the notebook's five dashboard tabs as one document."""

from datetime import datetime, timezone

from .calculations import escalation_status, evaluate, field_decision, netting_economics
from .data import (CASE_LABELS, FIELD_CASES, IPM, NET_CASE, NET_SIGNAL, NET_STAGE,
                   NETTING_DEFAULTS, OUT_OF_GATE_SCOPE, PLANS, SCENARIOS)


def fmt(x):
    return "Unknown" if x is None else f"{x:,.1f}".removesuffix(".0")


def span(values, unit):
    if values is None or any(v is None for v in values):
        return "Unknown"
    lo, hi = sorted(values)
    return f"{fmt(lo)}–{fmt(hi)} {unit}" if lo != hi else f"{fmt(lo)} {unit}"


def card(label, value, note):
    return dict(label=label, value=value, note=note)


def options():
    """Everything a client needs to build the report form."""
    return [
        dict(id=case, label=label, field_case=FIELD_CASES[case]["title"],
             stages=FIELD_CASES[case]["stages"],
             impact_defaults=SCENARIOS[case]["inputs"] if case in SCENARIOS else None,
             netting_defaults=NETTING_DEFAULTS if case == NET_CASE else None)
        for case, label in CASE_LABELS.items()
    ]


def resolve_selection(case, stage=None, observation=None):
    """Validate the case and fill in the first stage/observation when they're omitted."""
    if case not in CASE_LABELS:
        raise ValueError(f"Unknown case {case!r}. Choose one of: {', '.join(CASE_LABELS)}.")
    stages = FIELD_CASES[case]["stages"]
    stage = stage or next(iter(stages))
    if stage not in stages:
        raise ValueError(f"Unknown stage {stage!r} for {case}. Choose one of: {', '.join(stages)}.")
    observation = observation or stages[stage][0]
    if observation not in stages[stage]:
        raise ValueError(f"Unknown observation {observation!r} for this stage. Choose one of: {', '.join(stages[stage])}.")
    return case, stage, observation


def netting_active(case, stage, observation):
    return (case, stage, observation) == (NET_CASE, NET_STAGE, NET_SIGNAL)


def scenario_impact(case, overrides, recovered, added_co2):
    s = SCENARIOS[case]
    inputs = {**s["inputs"], **{k: v for k, v in (overrides or {}).items() if v is not None}}
    r = evaluate(**inputs, recovered=recovered, added_co2=added_co2)

    note = s["note"]
    if r["after"] is None:
        note += " Enter an assumed recovery to simulate the action. Its effect is unverified."
    else:
        note += f" With the assumed recovery, remaining shortfall: {span(r['after'], 't')}."

    return dict(
        kind="scenario",
        context="This is a separate illustrative scenario for this crop. Its costs and effects "
                "have not been established for the selected field action.",
        scenario=dict(name=s["scenario"], hazard=s["hazard"], action=s["action"]),
        inputs=dict(inputs, recovered=recovered, added_co2=added_co2),
        result=r,
        sections=[
            dict(title="Cultivation", note=note, cards=[
                card("Current plan", span(r["usable"], "usable t"),
                     f"Shortfall {span(r['gap'], 't')} · replacement premium {span(r['cost'], '€')}"),
                card(s["action"], span(r["action_cost"], "€ total added cost"),
                     f"Break-even: {fmt(r['break_even'])} t avoided" if r["break_even"] is not None
                     else "No replacement premium to offset action cost."),
                card("Arrange backup supply", span(r["gap"], "t to cover"),
                     "Verify supplier capacity, crop quality and delivery timing."),
            ]),
            dict(title="Carbon",
                 note="Enter a supported or illustrative emissions change to compare totals. Include a recovery "
                      "estimate to compare intensity. Replacement supply emissions are outside this demo boundary.",
                 cards=[
                     card("Baseline emissions", f"{fmt(r['carbon'])} t CO₂e",
                          "Illustrative contracted crop production boundary."),
                     card("Baseline intensity", span(r["intensity"], "kg CO₂e / usable t"),
                          "Total emissions divided by usable tonnes."),
                     card("Action emissions",
                          f"{fmt(r['action_carbon'])} t CO₂e" if r["action_carbon"] is not None else "Unknown",
                          f"Intensity: {span(r['action_intensity'], 'kg CO₂e / usable t')}."),
                 ]),
            dict(title="Resilient seeds",
                 note="This demo provides a search brief. Cultivars, suppliers and biotech candidates have yet to be verified.",
                 cards=[
                     card("Trait to screen", s["trait"], s["research"]),
                     card("Commercial seed search", s["seed_query"],
                          "Verify cultivar, regional suitability, availability and supplier before purchase."),
                     card("Biotech research", "Evidence needed",
                          "Track candidate genes, authorization, patents, licensing and seed access separately."),
                 ]),
        ],
    )


def netting_impact(case, stage, observation, netting):
    if not netting_active(case, stage, observation):
        return dict(kind="none",
                    context="No carrot baseline is loaded. Follow the selected scouting or diagnosis playbook. "
                            "The netting calculator applies to the preventive netting recommendation.",
                    sections=[])

    inputs = {**NETTING_DEFAULTS, **{k: v for k, v in (netting or {}).items() if v is not None and k != "saved"}}
    saved = (netting or {}).get("saved")
    r = netting_economics(**inputs, saved=saved)
    threshold, gain = r["break_even_tonnes"], r["net_gain_eur"]
    return dict(
        kind="netting",
        context="Carrot psyllid · action-specific economics. Illustrative inputs: net value per additional "
                "marketable tonne after any added harvest, handling or delivery costs.",
        inputs=dict(inputs, saved=saved),
        result=r,
        sections=[dict(
            title="Preventive netting · illustrative economics",
            note="Purchase cost is spread evenly across reuse seasons. Add storage or repairs to seasonal "
                 "costs if relevant. Yield benefit has not been verified.",
            cards=[
                card("Seasonal cost", f"€{r['seasonal_cost_eur']:,.0f}", f"{fmt(inputs['area'])} ha covered"),
                card("Break-even marketable crop saved",
                     "Unavailable at €0 per tonne" if threshold is None else f"{threshold:,.2f} t total",
                     "" if threshold is None else f"{threshold / inputs['area']:,.2f} t/ha"),
                card("Net benefit",
                     "Unknown" if gain is None else f"€{gain:,.0f}",
                     "Enter an assumed yield benefit" if gain is None else "Under your what-if assumption"),
            ],
        )],
    )


def build_report(case, stage=None, observation=None, impact=None, recovered=None, added_co2=None,
                 netting=None, checks=None):
    """The full report as plain data. Raises ValueError on invalid selections or inputs."""
    case, stage, observation = resolve_selection(case, stage, observation)
    field = FIELD_CASES[case]
    action, how, check_next = field_decision(case, stage, observation)

    checks = {"monitoring": False, "threshold_met": False, "alternatives_insufficient": False, **(checks or {})}
    in_scope = case not in OUT_OF_GATE_SCOPE
    status = escalation_status(in_scope, checks["monitoring"], checks["threshold_met"],
                               checks["alternatives_insufficient"])

    plan, measure, traits, species = PLANS[case]
    impact_section = (scenario_impact(case, impact, recovered, added_co2) if case in SCENARIOS
                      else netting_impact(case, stage, observation, netting))

    return dict(
        title="Climate Lens DSS",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        case=dict(id=case, label=CASE_LABELS[case], field_case=field["title"]),
        stage=stage,
        observation=observation,
        field_action=dict(
            action=action, how=how, check_next=check_next, biology=field["biology"],
            sources=[dict(label=label, url=url) for label, url in [*field["sources"], ("Tukes IPM", IPM)]],
        ),
        escalation=dict(
            in_scope=in_scope, checks=checks if in_scope else None, status=status,
            guidance="Record the pest, crop stage, observation, threshold source and date. This gate records your "
                     "checks and never authorizes a treatment or supplies a dose. Any chemical option needs a "
                     "current Finnish authorization and label check.",
            source=dict(label="Tukes IPM guidance", url=IPM),
        ),
        cultivation_plan=dict(plan=plan, measure=measure),
        impact=impact_section,
        breeding=dict(
            traits=traits,
            verification="Verify cultivar identity, trial location and years, commercial availability, "
                         "and buyer quality requirements before ranking.",
        ),
        biotech=dict(
            species=species,
            guidance="Define the trait and compare against conventional varieties. Record candidate gene, "
                     "supporting study, regulatory status, patent claims and separate licensing or material "
                     "access evidence.",
            status="Verified genes, suppliers and licenses have yet to be added.",
        ),
    )
