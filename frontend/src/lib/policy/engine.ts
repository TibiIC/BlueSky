/**
 * Policy → warming → risk engine. Pure functions, run in the browser so the map reacts instantly.
 *
 * 1. World policies set an ambition score s ∈ [0, 1] (sum of the active cards' emission shares).
 * 2. s picks the pathway: s = 0 is current policies (≈ SSP5-8.5 in the package's NGFS mapping),
 *    s = 0.5 pledges/NDCs (≈ SSP2-4.5), s = 1 net zero (≈ SSP1-2.6). Global warming at any year
 *    is interpolated between the three AR6 pathways.
 * 3. Each climate cell's risk indicators follow their fitted slope against warming level
 *    (lens/build_data.py → warming.json), giving a change vs 1991–2020 scored −1 (worse) … +1 (better).
 * 4. Prices (carbon, ETS2, fertiliser) interpolate between the package's NGFS-style scenarios.
 * 5. "Here" policies change Apetit-specific outcomes (peat, catch crops, input costs) for an area,
 *    scaled by how far farmers actually comply with them (prices are unaffected).
 */
import catalogue from './policies.json' with { type: 'json' };

export type Group = 'world' | 'here' | 'costs';
export interface Policy {
	id: string;
	group: Group;
	title: string;
	status: 'adopted' | 'pledged' | 'proposed' | 'speculative';
	meterWeight?: number;
	effects?: {
		peatRestoredShare?: Record<string, number>;
		catchCropShare?: number;
		dieselCarbonPrice?: boolean;
		fertiliserCarbonPrice?: boolean;
	};
	summary: string;
	lever?: string;
	source: string;
}
export const POLICIES = catalogue.policies as Policy[];
export const POLICY_NOTE = catalogue.note;

export interface ComplianceOption {
	id: string;
	/** Share of the required practice that actually happens on farms, 0–1. */
	share: number;
	label: string;
	summary: string;
}
export const COMPLIANCE = catalogue.compliance as {
	title: string;
	summary: string;
	default: string;
	options: ComplianceOption[];
	sources: string[];
};
export const DEFAULT_COMPLIANCE = COMPLIANCE.options.find((o) => o.id === COMPLIANCE.default)!.share;

type Scen = 'ssp126' | 'ssp245' | 'ssp585';
interface Fit {
	base: number;
	slope: number;
	r2: number;
}
export interface Warming {
	baselineGwl: number;
	gwl: Record<Scen, Record<'2030s' | '2040s' | '2050s', number>>;
	ar6: { bestEstimate: Record<Scen, [number, number, number]> };
	cells: Record<string, Record<string, Fit>>;
}
interface TransitionScenario {
	ssp: Scen;
	years: number[];
	carbonPrice: number[];
	ets2Price: number[];
	nFertiliserIndex: number[];
	dieselIndex: number[];
	importPremiumPct: number[];
}
export interface Transition {
	scenarios: Record<'current_policies' | 'ndcs' | 'below_2c' | 'net_zero_2050', TransitionScenario>;
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
/** Piecewise-linear interpolation of y over increasing x. */
function interp(x: number, xs: number[], ys: number[]): number {
	if (x <= xs[0]) return ys[0];
	for (let i = 1; i < xs.length; i++) if (x <= xs[i]) return lerp(ys[i - 1], ys[i], (x - xs[i - 1]) / (xs[i] - xs[i - 1]));
	return ys.at(-1)!;
}

// ---- 1–2. World ambition and warming ------------------------------------------------------

/** World ambition score: share of global emissions whose net-zero policy is switched on. */
export function ambition(active: Set<string>): number {
	return clamp(POLICIES.filter((p) => active.has(p.id)).reduce((s, p) => s + (p.meterWeight ?? 0), 0), 0, 1);
}

/** AR6 best-estimate period centres, with 1991–2020 as the first point. */
const CENTRES = [2005.5, 2030.5, 2050.5, 2090.5];

function gwlFor(scen: Scen, year: number, w: Warming): number {
	const [a, b, c] = w.ar6.bestEstimate[scen];
	return interp(year, CENTRES, [w.baselineGwl, a, b, c]);
}

/** Global warming (°C above 1850–1900) in `year` for ambition s. */
export function warmingAt(s: number, year: number, w: Warming): number {
	const hi = gwlFor('ssp585', year, w), mid = gwlFor('ssp245', year, w), lo = gwlFor('ssp126', year, w);
	return s <= 0.5 ? lerp(hi, mid, s / 0.5) : lerp(mid, lo, (s - 0.5) / 0.5);
}

/** Nearest SSP label for display. */
export function sspLabel(s: number): string {
	return s < 0.25 ? 'SSP5-8.5' : s < 0.75 ? 'SSP2-4.5' : 'SSP1-2.6';
}
export function ambitionLabel(s: number): string {
	return s < 0.2 ? 'Current policies' : s < 0.6 ? 'Partial pledges' : s < 0.9 ? 'Most pledges met' : 'Net zero delivered';
}

// ---- 3. Risks per climate cell -----------------------------------------------------------

export type RiskId = 'composite' | 'peaHeat' | 'drought' | 'wetHarvest' | 'season' | 'lateFrost';
interface RiskDef {
	label: string;
	short: string;
	/** Indicator in warming.json; composite averages the others. */
	indicator?: string;
	/** Change that scores a full −1 (worse) when positive-is-bad, or +1 when positive-is-good. */
	scale: number;
	/** +1: an increase is bad for Apetit; −1: an increase is good. */
	badIfUp: 1 | -1;
	unit: string;
	explain: string;
}
export const RISKS: Record<RiskId, RiskDef> = {
	composite: { label: 'Composite crop risk', short: 'Composite', scale: 1, badIfUp: 1, unit: '', explain: 'Average of pea heat, drought and wet-harvest scores.' },
	peaHeat: { label: 'Pea heat stress', short: 'Pea heat', indicator: 'pHeatSeason', scale: 0.4, badIfUp: 1, unit: 'share of seasons', explain: 'Seasons with ≥ 8 days ≥ 27 °C in June–July, when peas flower and fill pods. The main driver of bad pea years in the data.' },
	drought: { label: 'Early-summer drought', short: 'Drought', indicator: 'waterBalanceMJJA', scale: 50, badIfUp: -1, unit: 'mm', explain: 'May–Aug rain minus evaporation. Lower is drier.' },
	wetHarvest: { label: 'Wet harvest', short: 'Wet harvest', indicator: 'heavyRainDaysJAS', scale: 1, badIfUp: 1, unit: 'days', explain: 'Days with ≥ 20 mm rain in Jul–Sep: delayed harvest, intake bunching, field damage.' },
	season: { label: 'Longer growing season', short: 'Season', indicator: 'gdd5', scale: 500, badIfUp: -1, unit: '°C·days', explain: 'Growing degree days above 5 °C. An opportunity: new varieties and crops become possible.' },
	lateFrost: { label: 'Late spring frost', short: 'Late frost', indicator: 'frostDaysMay', scale: 0.5, badIfUp: 1, unit: 'days', explain: 'Frost days in May that hit emerging crops. Falls with warming.' }
};
const COMPOSITE: RiskId[] = ['peaHeat', 'drought', 'wetHarvest'];

export interface CellRisk {
	/** −1 (much worse than 1991–2020) … +1 (much better). */
	score: number;
	/** Indicator change vs 1991–2020 (undefined for composite). */
	delta?: number;
	value?: number;
	/** Fit R² (0–1): how consistently the three scenario runs agree. */
	confidence: number;
}

export function cellRisk(risk: RiskId, cell: Record<string, Fit>, gwl: number, w: Warming): CellRisk {
	if (risk === 'composite') {
		const parts = COMPOSITE.map((r) => cellRisk(r, cell, gwl, w));
		return {
			score: parts.reduce((s, p) => s + p.score, 0) / parts.length,
			confidence: parts.reduce((s, p) => s + p.confidence, 0) / parts.length
		};
	}
	const def = RISKS[risk];
	const fit = cell[def.indicator!];
	const delta = fit.slope * (gwl - w.baselineGwl);
	let value = fit.base + delta;
	if (def.indicator === 'pHeatSeason') value = clamp(value, 0, 1);
	// `+ 0` turns −0 into 0 so the UI never shows "−0".
	return { score: clamp((-def.badIfUp * delta) / def.scale, -1, 1) + 0, delta: delta + 0, value, confidence: clamp(fit.r2, 0, 1) };
}

/** Red (−1) → amber (0) → green (+1). */
export function riskColor(score: number): [number, number, number] {
	const red = [214, 64, 69], amber = [236, 196, 94], green = [86, 170, 112];
	const [a, b, t] = score < 0 ? [amber, red, -score] : [amber, green, score];
	return a.map((v, i) => Math.round(lerp(v, b[i], t))) as [number, number, number];
}

// ---- 4. Prices ---------------------------------------------------------------------------

export interface Prices {
	year: number;
	carbonPrice: number;
	ets2Price: number;
	nFertiliserIndex: number;
	dieselIndex: number;
	importPremiumPct: number;
}

/** Interpolates the package's NGFS-style scenarios: s = 0 current policies … 1 net zero 2050. */
export function pricesAt(s: number, year: number, t: Transition): Prices {
	const order: [number, TransitionScenario][] = [
		[0, t.scenarios.current_policies],
		[0.5, t.scenarios.ndcs],
		[0.75, t.scenarios.below_2c],
		[1, t.scenarios.net_zero_2050]
	];
	const pick = (k: keyof Omit<TransitionScenario, 'ssp' | 'years'>) =>
		interp(s, order.map(([x]) => x), order.map(([, sc]) => interp(year, sc.years, sc[k])));
	return {
		year,
		carbonPrice: pick('carbonPrice'),
		ets2Price: year < 2028 ? 0 : pick('ets2Price'),
		nFertiliserIndex: pick('nFertiliserIndex'),
		dieselIndex: pick('dieselIndex'),
		importPremiumPct: pick('importPremiumPct')
	};
}

// ---- 5. Apetit outcomes from "here" policies ---------------------------------------------

/** Diesel: 2.10 kg CO₂/l (Finnish bio-blend, METHODOLOGY.md §5). AN fertiliser: 3.7 kg CO₂e/kg N. */
const DIESEL_T_CO2_PER_L = 0.0021;
const AN_T_CO2E_PER_KG_N = 0.0037;

export interface AreaFacts {
	contractPeatCo2e: number;
	organicContractHa: number;
	peaSpinachHa: number;
	peaSpinachCatchHa: number;
	catchCropEurPerT?: number | null;
}
export interface Outcomes {
	peatCo2eAvoided: number;
	peatHaOutOfCrops: number;
	catchCropHaAdded: number;
	dieselEurPerL: number;
	fertiliserEurPerKgN: number;
}

/**
 * `compliance` (0–1) is the share of each rule's required practice that farms actually carry out.
 * Catch crops already grown voluntarily count in full; compliance applies to the extra hectares.
 */
export function outcomes(active: Set<string>, year: number, prices: Prices, area: AreaFacts | null, compliance = 1): Outcomes {
	const on = POLICIES.filter((p) => active.has(p.id));
	const decade = String(year < 2035 ? 2030 : year < 2045 ? 2040 : 2050);
	const peatShare = Math.max(0, ...on.map((p) => p.effects?.peatRestoredShare?.[decade] ?? 0)) * compliance;
	const catchShare = Math.max(0, ...on.map((p) => p.effects?.catchCropShare ?? 0));
	return {
		peatCo2eAvoided: area ? area.contractPeatCo2e * peatShare : 0,
		peatHaOutOfCrops: area ? area.organicContractHa * peatShare : 0,
		catchCropHaAdded: area ? Math.max(0, area.peaSpinachHa * catchShare - area.peaSpinachCatchHa) * compliance : 0,
		dieselEurPerL: on.some((p) => p.effects?.dieselCarbonPrice) ? DIESEL_T_CO2_PER_L * prices.ets2Price : 0,
		fertiliserEurPerKgN: on.some((p) => p.effects?.fertiliserCarbonPrice) ? AN_T_CO2E_PER_KG_N * prices.carbonPrice : 0
	};
}
