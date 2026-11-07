"""Decision logic and calculators, ported unchanged from FinlandIP_DSS.ipynb."""

import math

from .data import FIELD_CASES


def evaluate(area, yield_low, yield_high, demand, premium, action_cost,
             baseline_co2, recovered=None, added_co2=None):
    """Supply shortfall, replacement cost and carbon intensity as (low, high) yield ranges."""
    values = [area, yield_low, yield_high, demand, premium, action_cost, baseline_co2]
    if any(not math.isfinite(x) or x < 0 for x in values) or yield_low > yield_high:
        raise ValueError("Use nonnegative finite inputs and a low yield no greater than high yield.")
    if recovered is not None and (not math.isfinite(recovered) or recovered < 0):
        raise ValueError("Recovered tonnes must be nonnegative and finite.")
    if added_co2 is not None and not math.isfinite(added_co2):
        raise ValueError("Emissions change must be finite.")
    usable = (area * yield_low, area * yield_high)
    gap = tuple(max(0, demand - x) for x in usable)
    after = None if recovered is None else tuple(max(0, x - recovered) for x in gap)
    action_total = None if added_co2 is None else baseline_co2 + added_co2
    if action_total is not None and action_total < 0:
        raise ValueError("The resulting emissions cannot be negative.")
    intensity = lambda total, tonnes: tuple(total * 1000 / x if x > 0 else None for x in tonnes)
    action_yield = None if after is None else tuple(u + g - a for u, g, a in zip(usable, gap, after))
    return dict(usable=usable, gap=gap, cost=tuple(x * premium for x in gap),
                break_even=action_cost / premium if premium else None,
                after=after, action_cost=None if after is None else tuple(action_cost + x * premium for x in after),
                carbon=baseline_co2, intensity=intensity(baseline_co2, usable),
                action_carbon=action_total,
                action_intensity=None if action_total is None or action_yield is None else intensity(action_total, action_yield))


def netting_economics(area, price, seasons, labor, value, saved=None):
    """Seasonal cost and break-even tonnes for preventive insect netting."""
    inputs = [area, price, seasons, labor, value]
    if any(not math.isfinite(x) or x < 0 for x in inputs) or area == 0 or seasons < 1:
        raise ValueError("Use positive hectares, at least one season, and nonnegative costs.")
    if saved is not None and (not math.isfinite(saved) or saved < 0):
        raise ValueError("Enter a nonnegative estimate of saved tonnes.")
    cost = area * (price / seasons + labor)
    return {
        "seasonal_cost_eur": cost,
        "break_even_tonnes": cost / value if value else None,
        "assumed_saved_tonnes": saved,
        "net_gain_eur": None if saved is None else saved * value - cost,
    }


def field_decision(case, stage, signal):
    """(action, how, check next) playbook for a case, crop stage and field observation."""
    stages = FIELD_CASES[case]["stages"]
    if stage not in stages or signal not in stages[stage]:
        raise ValueError("Select a valid crop stage and observation.")
    if case == "satakunta-carrots":
        if stage == "Pre-emergence / emergence" and signal.startswith("Local"):
            return ("Fit insect netting before exposure", "Install fine mesh (0.6 × 0.6 mm or smaller) by the start of emergence. Seal every edge to the soil and check for tears or lifted edges after field access or wind.", "Confirm local flight and agree when covers can be opened with the grower. Log install date, mesh size and observations.")
        if stage == "Seedlings up to four leaves" and signal.startswith("Adults"):
            return ("Scout immediately and inspect cover integrity", "Inspect young leaves and check inside and outside any cover. Repair gaps. If uncovered, ask the grower adviser whether netting can still prevent further entry without enclosing pests already present.", "Photograph and record adults and symptoms. Existing injury will need separate assessment.")
        if stage == "Later growth":
            return ("Check the cause before choosing a control", "Inspect roots and field patterns. Ask an adviser to distinguish psyllid-associated symptoms from carrot fly, nutrition, compaction or excess moisture.", "Do not infer the cause from discoloration alone.")
        return ("Set up monitoring and prepare netting", "Check local flight reports, inspect seedlings and confirm net availability. In at-risk fields, the installation window closes at the start of emergence.", "Confirm field history and review the plan with the grower before emergence.")
    if case == "sakyla-peas":
        if stage == "Pod fill / harvest":
            return ("Sample pods and flag affected lots", "Open representative pods, record damage and notify quality or harvest leads. Follow the buyer's acceptance process.", "Record affected areas for next season's trap placement and rotation review.")
        if signal.startswith("Pheromone"):
            return ("Check whether flight overlaps susceptible crop stages", "Record trap catches and crop stage, inspect pods and consult local advisers on interpretation. Prioritize plots with sustained catches or prior damage.", "Trap detection alone does not establish a Finnish treatment threshold.")
        return ("Prepare or check pheromone traps", "Prioritize fields with prior damage or nearby pea production. Log catches alongside flowering and early pod development.", "Use local monitoring before deciding whether an intervention is justified.")
    if stage == "Spring regrowth":
        return ("Measure surviving stands before changing supply plans", "Sample live plants across representative zones, map gaps and review the stand with an adviser. Compare keeping the crop with reseeding and backup procurement.", "Use local crop and contract criteria before setting a minimum viable stand.")
    if stage == "Autumn establishment":
        return ("Diagnose establishment problems before winter", "Map weak patches and inspect seedbed, drainage and emergence. Record sowing date, variety and stand density.", "Set spring sampling points in affected and healthy zones.")
    return ("Compare locally tested varieties and spring alternatives", "Review trial survival and yield across seasons. Compare alternative winter varieties or spring forms with the current rotation.", "Use local multi-season evidence, grower costs and contract requirements before ranking.")


def escalation_status(in_scope, monitored, threshold_met, options_insufficient):
    """Non-chemical-first gate. Records checks; never authorizes a treatment."""
    if not in_scope:
        return "Outside this pest-control workflow"
    if not monitored or not threshold_met:
        return "Continue prevention and monitoring"
    if not options_insufficient:
        return "Prioritize feasible non-chemical options"
    return "Refer to a qualified adviser for review"
