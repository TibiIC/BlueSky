import type { Polygon } from 'geojson';
import { bbox, booleanPointInPolygon } from '@turf/turf';
import {
	DECADES,
	SCENARIOS,
	type ClimateIndicators,
	type Decade,
	type LensAction,
	type LensCatchment,
	type LensResult,
	type Scenario
} from './types.ts';

/** Static files written by `python3 lens/build_data.py` into frontend/static/data/lens. */
const DATA_URL = '/data/lens';

interface Parcels {
	id: string[];
	farm: string[];
	lon: number[];
	lat: number[];
	area: number[];
	soil: string[];
	distWater: number[];
	catchment: string[];
	pTest: (number | null)[];
	buffer: boolean[];
	crop: string[];
	catchCrop: boolean[];
	contract: boolean[];
	cell: string[];
	peatCo2e: number[];
}
interface Farm {
	segment: string;
	region: string;
	country: string;
	contractHa: number | null;
	organicShare: number | null;
	soilReported: string | null;
	survey?: { id: string; crop: string; fertiliser: string; irrigated: boolean }[];
}
interface CellIndicators {
	periods: Record<string, ClimateIndicators | Record<Scenario, ClimateIndicators>>;
	history: { years: number[]; hotDaysJJ: number[]; waterBalanceMJJA: number[] };
}
interface Lever {
	id: string;
	name: string;
	flag: boolean;
	abatement2030: number;
	eurPerT: number | null;
	start: number;
	confidence: string | null;
	coBenefits: string | null;
	tradeOffs: string | null;
}
interface Data {
	parcels: Parcels;
	farms: Record<string, Farm>;
	catchments: { features: { properties: { id: string; water: string; status: string; pSensitivity: number; contractHa: number; monitored: boolean; load?: { year: number; pKg: number; nKg: number } } }[] };
	climate: { indicators: Record<string, CellIndicators> };
	levers: { levers: Lever[]; prices: { year: number; items: Record<string, { eurPerT: number; replacementPremium: number }> } };
	meta: {
		package: string;
		version: string;
		builtAt: string;
		reportYear: number;
		notice: string;
		sources: Record<string, { path: string; sha256: string | null }>;
		constants: Record<string, unknown>;
	};
}

const SOURCE_LABELS: Record<string, string> = {
	parcels: 'Field parcels (soil map, slope, water distance)',
	farms: 'Contract-farm registry',
	cells: 'Climate grid cells',
	crop_history: 'Crop per parcel and year',
	farm_survey: 'Finnish farm survey (self-reported)',
	calculator: 'Current calculator footprints (mineral soil assumed)',
	weather: 'Daily weather 1991–2060, three SSP scenarios',
	catchments: 'Catchment status and sensitivity',
	catchment_geo: 'Catchment polygons',
	loads: 'Monitored outlet nutrient loads',
	levers: 'Decarbonisation lever catalogue (design estimates)',
	prices: 'Contract prices and replacement premiums',
	method_peat: 'METHODOLOGY.md §5: drained organic soils'
};

let cache: Promise<{ data: Data } | null> | null = null;

/** Loads the lens files once per server process through SvelteKit's fetch (works with any adapter). */
export function loadLensData(fetcher: typeof fetch): Promise<{ data: Data } | null> {
	cache ??= (async () => {
		const read = async <T>(name: string): Promise<T> => {
			const res = await fetcher(`${DATA_URL}/${name}`);
			if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
			return (await res.json()) as T;
		};
		try {
			const [parcels, farms, catchments, climate, levers, meta] = await Promise.all([
				read<Parcels>('parcels.json'),
				read<Record<string, Farm>>('farms.json'),
				read<Data['catchments']>('catchments.geojson'),
				read<Data['climate']>('climate.json'),
				read<Data['levers']>('levers.json'),
				read<Data['meta']>('meta.json')
			]);
			return { data: { parcels, farms, catchments, climate, levers, meta } };
		} catch (e) {
			console.warn('[lens] data unavailable:', e);
			cache = null; // retry on the next request, e.g. after running the build script
			return null;
		}
	})();
	return cache;
}

const round = (v: number, nd = 1) => Math.round(v * 10 ** nd) / 10 ** nd;
const add = (m: Record<string, number>, k: string, v: number) => (m[k] = (m[k] ?? 0) + v);
const roundValues = (m: Record<string, number>) =>
	Object.fromEntries(Object.entries(m).sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, round(v)]));

const STATE_WEIGHT: Record<string, number> = { good: 1.0, moderate: 1.2, poor: 1.5, bad: 1.8 };
const KEYS: (keyof ClimateIndicators)[] = ['tmeanMJJA', 'hotDaysJJ', 'precipMJJA', 'waterBalanceMJJA', 'gdd5', 'frostDaysMay', 'heavyRainDaysJAS', 'pHeatSeason'];

/** Area-weighted mean of per-cell indicators. */
function blend(cells: Record<string, CellIndicators>, weights: Map<string, number>, pick: (c: CellIndicators) => ClimateIndicators): ClimateIndicators {
	const total = [...weights.values()].reduce((a, b) => a + b, 0);
	const out = {} as ClimateIndicators;
	for (const k of KEYS) {
		let s = 0;
		for (const [cell, w] of weights) s += (pick(cells[cell])[k] as number) * w;
		out[k] = round(s / total, k === 'pHeatSeason' ? 3 : 2);
	}
	out.years = pick(cells[weights.keys().next().value!]).years;
	return out;
}

/** Report on the contract parcels whose centroid lies inside any of the polygons. */
export async function lensReport(polygons: Polygon[], fetcher: typeof fetch): Promise<LensResult> {
	const loaded = await loadLensData(fetcher);
	if (!loaded) return { available: false, reason: 'Climate Lens data not built. Run: python3 lens/build_data.py' };
	const { data } = loaded;
	const P = data.parcels;
	const boxes = polygons.map((g) => bbox(g));

	const idx: number[] = [];
	for (let i = 0; i < P.id.length; i++) {
		const x = P.lon[i], y = P.lat[i];
		for (let k = 0; k < polygons.length; k++) {
			const [w, s, e, n] = boxes[k];
			if (x >= w && x <= e && y >= s && y <= n && booleanPointInPolygon([x, y], polygons[k])) {
				idx.push(i);
				break;
			}
		}
	}

	const cropHa: Record<string, number> = {};
	const soilHa: Record<string, number> = {};
	const cellHa = new Map<string, number>();
	const catchHa = new Map<string, number>();
	const farmIds = new Set<string>();
	let ha = 0, contractHa = 0, organicHa = 0, organicContractHa = 0, contractCo2e = 0, allCo2e = 0;
	let peaSpinachHa = 0, peaSpinachCatchHa = 0, carrotPotatoHa = 0, missingPTest = 0, nearWaterNoBuffer = 0;
	for (const i of idx) {
		const a = P.area[i];
		ha += a;
		farmIds.add(P.farm[i]);
		if (P.crop[i]) add(cropHa, P.crop[i], a);
		add(soilHa, P.soil[i], a);
		cellHa.set(P.cell[i], (cellHa.get(P.cell[i]) ?? 0) + a);
		catchHa.set(P.catchment[i], (catchHa.get(P.catchment[i]) ?? 0) + a);
		allCo2e += P.peatCo2e[i];
		if (P.soil[i] === 'organic') organicHa += a;
		if (P.contract[i]) {
			contractHa += a;
			contractCo2e += P.peatCo2e[i];
			if (P.soil[i] === 'organic') organicContractHa += a;
		}
		if (P.crop[i] === 'pea' || P.crop[i] === 'spinach') {
			peaSpinachHa += a;
			if (P.catchCrop[i]) peaSpinachCatchHa += a;
		}
		if (P.crop[i] === 'carrot' || P.crop[i] === 'potato') carrotPotatoHa += a;
		if (P.pTest[i] === null) missingPTest++;
		if (P.distWater[i] < 100 && !P.buffer[i]) nearWaterNoBuffer++;
	}

	const farms = [...farmIds].map((id) => [id, data.farms[id]] as const);
	const farmsBySegment: Record<string, number> = {};
	for (const [, f] of farms) add(farmsBySegment, f.segment, 1);
	const misreportCandidates = farms
		.filter(([, f]) => f.country === 'FI' && (f.organicShare ?? 0) >= 0.3 && f.soilReported !== 'Organic soil')
		.map(([farm, f]) => ({ farm, organicShare: f.organicShare!, reported: f.soilReported }))
		.sort((a, b) => b.organicShare - a.organicShare);

	const catchments: LensCatchment[] = data.catchments.features
		.filter((f) => catchHa.has(f.properties.id))
		.map(({ properties: c }) => ({
			id: c.id,
			water: c.water,
			status: c.status,
			pSensitivity: c.pSensitivity,
			contractHaInArea: round(catchHa.get(c.id)!),
			contractHaTotal: c.contractHa,
			load: c.load,
			monitored: c.monitored
		}))
		.sort((a, b) => b.pSensitivity * (STATE_WEIGHT[b.status] ?? 1) - a.pSensitivity * (STATE_WEIGHT[a.status] ?? 1));

	const meta = data.meta;
	const sources = Object.fromEntries(
		Object.entries(meta.sources).map(([k, v]) => [k, { ...v, label: SOURCE_LABELS[k] ?? k }])
	) as Record<string, { path: string; sha256: string | null; label: string }>;
	sources.method_peat = { path: 'docs/METHODOLOGY.md', sha256: null, label: SOURCE_LABELS.method_peat };

	const base = {
		available: true as const,
		notice: meta.notice,
		package: { name: meta.package, version: meta.version, builtAt: meta.builtAt, reportYear: meta.reportYear },
		prices: data.levers.prices,
		sources,
		constants: meta.constants
	};
	const fig = (value: number, unit: string, src: string[], nd = 1) => ({ value: round(value, nd), unit, src });

	const empty = idx.length === 0;
	const climate = empty
		? null
		: (() => {
				const dominant = [...cellHa.entries()].sort((a, b) => b[1] - a[1])[0][0];
				const future = {} as Record<Scenario, Record<Decade, ClimateIndicators>>;
				for (const s of SCENARIOS) {
					future[s] = {} as Record<Decade, ClimateIndicators>;
					for (const d of DECADES)
						future[s][d] = blend(data.climate.indicators, cellHa, (c) => (c.periods[d] as Record<Scenario, ClimateIndicators>)[s]);
				}
				return {
					cells: [...cellHa.keys()],
					baseline: blend(data.climate.indicators, cellHa, (c) => c.periods.baseline as ClimateIndicators),
					recent: blend(data.climate.indicators, cellHa, (c) => c.periods.recent as ClimateIndicators),
					future,
					history: data.climate.indicators[dominant].history,
					src: ['weather', 'cells', 'parcels']
				};
			})();

	const actions = empty
		? []
		: buildActions(data.levers.levers, {
				organicContractHa,
				organicHa,
				contractCo2e,
				contractHa,
				peaSpinachHa,
				peaSpinachCatchHa,
				carrotPotatoHa,
				parcels: idx.length,
				missingPTest,
				nearWaterNoBuffer,
				lowCarbonShare: lowCarbonShare(farms.map(([, f]) => f)),
				climate
			});

	return {
		...base,
		area: {
			parcels: idx.length,
			farms: farmIds.size,
			farmsBySegment,
			hectares: fig(ha, 'ha', ['parcels']),
			contractHectares: fig(contractHa, 'ha', ['parcels', 'crop_history']),
			cropHa: roundValues(cropHa),
			soilHa: roundValues(soilHa),
			regions: [...new Set(farms.map(([, f]) => f.region))]
		},
		peat: {
			organicHa: fig(organicHa, 'ha', ['parcels']),
			organicContractHa: fig(organicContractHa, 'ha', ['parcels', 'crop_history']),
			contractCo2e: fig(contractCo2e, 't CO₂e/yr', ['parcels', 'crop_history', 'method_peat'], 0),
			allCropsCo2e: fig(allCo2e, 't CO₂e/yr', ['parcels', 'crop_history', 'method_peat'], 0),
			misreportCandidates
		},
		catchments,
		climate,
		actions
	};
}

function lowCarbonShare(farms: Farm[]): number | null {
	const rows = farms.flatMap((f) => f.survey ?? []);
	if (!rows.length) return null;
	return rows.filter((r) => /low-carbon/i.test(r.fertiliser ?? '')).length / rows.length;
}

interface Facts {
	organicContractHa: number;
	organicHa: number;
	contractCo2e: number;
	contractHa: number;
	peaSpinachHa: number;
	peaSpinachCatchHa: number;
	carrotPotatoHa: number;
	parcels: number;
	missingPTest: number;
	nearWaterNoBuffer: number;
	lowCarbonShare: number | null;
	climate: { baseline: ClimateIndicators; future: Record<Scenario, Record<Decade, ClimateIndicators>> } | null;
}

/** Parcel-level levers (L08–L12, L24) that the area's own facts support. */
function buildActions(levers: Lever[], f: Facts): LensAction[] {
	const by = Object.fromEntries(levers.map((l) => [l.id, l]));
	const out: LensAction[] = [];
	const push = (id: string, evidence: string, src: string[], potential?: LensAction['potential']) => {
		const l = by[id];
		if (!l) return;
		out.push({
			id,
			name: l.name,
			flag: l.flag,
			evidence,
			potential,
			catalogue: { abatement2030: l.abatement2030, eurPerT: l.eurPerT, start: l.start, confidence: l.confidence, coBenefits: l.coBenefits, tradeOffs: l.tradeOffs },
			src: [...src, 'levers']
		});
	};
	const r1 = (v: number) => Math.round(v * 10) / 10;

	if (f.organicContractHa > 0)
		push(
			'L11',
			`${r1(f.organicContractHa)} ha of contract crops sit on drained organic soil (soil map, ~88 % accurate), emitting about ${Math.round(f.contractCo2e)} t CO₂e a year. The current calculator assumes mineral soil and misses this.`,
			['parcels', 'crop_history', 'method_peat', 'calculator'],
			{ value: Math.round(f.contractCo2e), unit: 't CO₂e/yr (upper bound)', src: ['parcels', 'crop_history', 'method_peat'] }
		);
	if (f.organicHa > 0)
		push('L12', `${r1(f.organicHa)} ha of organic soil in the area could host a rewetting or paludiculture pilot once retired from annual crops.`, ['parcels']);
	if (f.peaSpinachHa > 0) {
		const share = f.peaSpinachCatchHa / f.peaSpinachHa;
		push('L10', `${r1(f.peaSpinachHa)} ha of early-harvested pea and spinach; ${Math.round(share * 100)} % of it has a catch crop after harvest.`, ['crop_history']);
	}
	if (f.contractHa > 0) {
		push(
			'L09',
			`${f.missingPTest} of ${f.parcels} parcels lack a soil phosphorus test; ${f.nearWaterNoBuffer} lie within 100 m of water without a buffer strip.`,
			['parcels']
		);
		push(
			'L08',
			f.lowCarbonShare === null
				? `${r1(f.contractHa)} ha of contract crops; no survey responses in this area to show current fertiliser use.`
				: `${Math.round(f.lowCarbonShare * 100)} % of this area's ${2025} survey responses already use low-carbon AN fertiliser.`,
			['farm_survey', 'parcels']
		);
	}
	if (f.carrotPotatoHa > 0 && f.climate) {
		const b = f.climate.baseline.waterBalanceMJJA, fut = f.climate.future.ssp585['2050s'].waterBalanceMJJA;
		push(
			'L24',
			`${r1(f.carrotPotatoHa)} ha of carrot and potato. May–Aug water balance moves from ${Math.round(b)} mm (1991–2020) to ${Math.round(fut)} mm in the 2050s under SSP5-8.5.`,
			['crop_history', 'weather']
		);
	}
	return out;
}
