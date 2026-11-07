"""Illustrative cases, playbook trees and planning text from FinlandIP_DSS.ipynb.

Replace these with the team's records once they are mapped to the same shape.
"""

LUKE = "https://www.luke.fi/fi/luonnonvaratieto/tiedetta-ja-tietoa/ipm-oppaat/porkkana/porkkanan-tuholaistorjunta"
APETIT = "https://apetit.fi/2022/10/03/hyonteisverkoilla-varmempi-ja-laadukkaampi-sato-viljelija-nakee-selkean-eron-satotasoon/"
IPM = "https://tukes.fi/en/safe-use-of-plant-protection-products/integrated-pest-management"
PEA = "https://horticulture.ahdb.org.uk/knowledge-library/biology-and-management-of-the-pea-moth"
VARPSI = "https://pyhajarvi-instituutti.fi/hanke/rypsin-ja-rapsinviljelyvarmuuden-ja-maaran-lisaaminen/"

# Impact calculator baselines (cost & carbon). Carrots have none loaded.
SCENARIOS = {
    "sakyla-peas": dict(
        crop="Frozen peas", site="Säkylä", scenario="Wet harvest · illustrative",
        hazard="A narrow harvest window may concentrate deliveries.",
        trait="Harvest-window flexibility", action="Stagger sowing", seed_query="Pisum sativum",
        research="Screen maturity timing and quality retention across harvest dates.",
        note="Confirm field access, maturity and factory intake before changing the schedule.",
        inputs=dict(area=100, yield_low=4, yield_high=5, demand=500, premium=40,
                    action_cost=1200, baseline_co2=82),
    ),
    "kantvik-rapeseed": dict(
        crop="Winter rapeseed", site="Kantvik", scenario="Winter stress · illustrative",
        hazard="Poor overwintering may reduce the volume available for crushing.",
        trait="Winter survival", action="Trial an alternative winter variety", seed_query="Brassica napus",
        research="Compare survival, usable yield and oil quality in local variety trials.",
        note="Check rotation, local winter survival evidence and grower constraints before choosing a variety.",
        inputs=dict(area=200, yield_low=1.5, yield_high=2.2, demand=480, premium=65,
                    action_cost=2600, baseline_co2=95),
    ),
}

# Field playbook trees: biology, {stage: [observations]}, sources.
FIELD_CASES = {
    "satakunta-carrots": dict(
        title="Satakunta carrots · carrot psyllid",
        biology="Overwintered adults move into carrots in early to mid-June in Finnish observations. The most vulnerable plants are at cotyledon to four-leaf stage. Adult feeding can curl young leaves, and discoloration can emerge later and has other possible causes.",
        stages={
            "Pre-emergence / emergence": ["Local flight reported or field has a history of psyllid damage", "No local flight signal or history known"],
            "Seedlings up to four leaves": ["Adults or curled young leaves observed", "No local flight signal or history known"],
            "Later growth": ["Discoloration or poor growth observed"],
        },
        sources=[("Luke Finnish carrot IPM guide", LUKE), ("Apetit grower netting case", APETIT)],
    ),
    "sakyla-peas": dict(
        title="Säkylä peas · pea moth",
        biology="Larvae overwinter in soil cocoons. Adults emerge and lay eggs on pea plants. Hatched larvae enter young pods, then leave mature pods and return to the soil. UK calendar dates in the linked source are not Finnish flight dates.",
        stages={
            "Before flowering": ["Field or nearby pea fields have a damage history", "No flight or damage information"],
            "Flowering / young pods": ["Pheromone traps detect moths", "No flight or damage information"],
            "Pod fill / harvest": ["Larvae or damaged pods observed"],
        },
        sources=[("AHDB pea moth biology and monitoring", PEA)],
    ),
    "kantvik-rapeseed": dict(
        title="Kantvik winter rapeseed · overwintering",
        biology="Establishment precedes winter exposure. Spring stand assessment separates establishment problems from possible overwintering losses. VARPSI treats winter survival as a key uncertainty.",
        stages={
            "Autumn establishment": ["Poor or patchy establishment"],
            "Spring regrowth": ["Stand gaps or suspected winterkill"],
            "Next-season planning": ["Repeated winter losses in local fields"],
        },
        sources=[("Finnish VARPSI oilseed project", VARPSI)],
    ),
}

# The cases a report can be generated for, in display order.
CASE_LABELS = {
    "satakunta-carrots": "Satakunta · Carrots",
    "sakyla-peas": "Säkylä · Frozen peas",
    "kantvik-rapeseed": "Kantvik · Winter rapeseed",
}

# Cultivation plan, what to measure, breeding traits, species for biotech search.
PLANS = {
    "sakyla-peas": (
        "Compare maturity groups and staggered sowing against the factory intake calendar.",
        "Record flowering, trap catches, young pod damage, marketable yield and delivery times.",
        "Screen maturity timing and freezing quality. For pea moth, compare damage under similar pest pressure and separate resistance from simply missing the moth flight window.",
        "Pisum sativum",
    ),
    "kantvik-rapeseed": (
        "Compare winter and spring forms, rotation fit, drainage and local establishment records.",
        "Record autumn stands, spring survival, usable yield and oil quality across sites and years.",
        "Screen winter survival and yield stability using local multi-season variety trials.",
        "Brassica napus",
    ),
    "satakunta-carrots": (
        "Plan monitoring and cover access before emergence. Compare covered and uncovered strips only where appropriate and agreed with the grower.",
        "Record flight observations, leaf injury, marketable root yield, labor and net reuse.",
        "Screen root quality and tolerance to locally confirmed damage. Compare conventional varieties alongside the existing netting practice.",
        "Daucus carota",
    ),
}

# The preventive netting recommendation the netting calculator applies to.
NET_CASE = "satakunta-carrots"
NET_STAGE = "Pre-emergence / emergence"
NET_SIGNAL = "Local flight reported or field has a history of psyllid damage"
NETTING_DEFAULTS = dict(area=5, price=1200, seasons=4, labor=200, value=250)

# Rapeseed overwintering is not a pest problem, so the chemical gate doesn't apply.
OUT_OF_GATE_SCOPE = {"kantvik-rapeseed"}
