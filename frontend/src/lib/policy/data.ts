import type { Polygon } from 'geojson';
import { bbox, booleanPointInPolygon } from '@turf/turf';
import { cellRisk, type AreaFacts, type CellRisk, type RiskId, type Transition, type Warming } from './engine.ts';

/** Columns of parcels.json used here (see lens/build_data.py). */
export interface ParcelCols {
	lon: number[];
	lat: number[];
	area: number[];
	soil: string[];
	crop: string[];
	catchCrop: boolean[];
	contract: boolean[];
	cell: string[];
	peatCo2e: number[];
}
export interface GridCell {
	id: string;
	region: string;
	lat: number;
	lon: number;
}
export interface PolicyData {
	warming: Warming;
	transition: Transition;
	cells: GridCell[];
	parcels: ParcelCols;
}

let cache: Promise<PolicyData | null> | null = null;

/** Loads the files written by `python3 lens/build_data.py` once per page. */
export function loadPolicyData(): Promise<PolicyData | null> {
	cache ??= (async () => {
		try {
			const get = (n: string) => fetch(`/data/lens/${n}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${n}: HTTP ${r.status}`))));
			const [warming, transition, climate, parcels] = await Promise.all([
				get('warming.json'),
				get('transition.json'),
				get('climate.json'),
				get('parcels.json')
			]);
			return { warming, transition, cells: climate.cells, parcels };
		} catch (e) {
			console.warn('[policy] data unavailable (run python3 lens/build_data.py):', e);
			cache = null;
			return null;
		}
	})();
	return cache;
}

export interface Area extends AreaFacts {
	parcels: number;
	hectares: number;
	contractHa: number;
	/** Hectares per climate cell, for area-weighted risk. */
	cellHa: Map<string, number>;
}

/** Facts for the parcels whose centroid is inside `polygon`, or for all contract parcels when null. */
export function areaFacts(p: ParcelCols, polygon: Polygon | null): Area {
	const box = polygon ? bbox(polygon) : null;
	const out: Area = {
		parcels: 0,
		hectares: 0,
		contractHa: 0,
		contractPeatCo2e: 0,
		organicContractHa: 0,
		peaSpinachHa: 0,
		peaSpinachCatchHa: 0,
		cellHa: new Map()
	};
	for (let i = 0; i < p.lon.length; i++) {
		if (box && polygon) {
			const x = p.lon[i], y = p.lat[i];
			if (x < box[0] || x > box[2] || y < box[1] || y > box[3] || !booleanPointInPolygon([x, y], polygon)) continue;
		}
		const a = p.area[i];
		out.parcels++;
		out.hectares += a;
		out.cellHa.set(p.cell[i], (out.cellHa.get(p.cell[i]) ?? 0) + a);
		if (p.contract[i]) {
			out.contractHa += a;
			out.contractPeatCo2e += p.peatCo2e[i];
			if (p.soil[i] === 'organic') out.organicContractHa += a;
		}
		if (p.crop[i] === 'pea' || p.crop[i] === 'spinach') {
			out.peaSpinachHa += a;
			if (p.catchCrop[i]) out.peaSpinachCatchHa += a;
		}
	}
	return out;
}

export interface AreaRisk {
	score: number;
	value?: number;
	base?: number;
	confidence: number;
}

/** Area-weighted risk over the climate cells that hold the area's parcels. */
export function areaRisk(risk: RiskId, cellHa: Map<string, number>, gwl: number, w: Warming): AreaRisk | null {
	let total = 0, score = 0, value = 0, base = 0, conf = 0, hasValue = true;
	for (const [cell, ha] of cellHa) {
		const fits = w.cells[cell];
		if (!fits) continue;
		const r: CellRisk = cellRisk(risk, fits, gwl, w);
		total += ha;
		score += r.score * ha;
		conf += r.confidence * ha;
		if (r.value === undefined || r.delta === undefined) hasValue = false;
		else {
			value += r.value * ha;
			base += (r.value - r.delta) * ha;
		}
	}
	if (!total) return null;
	return {
		score: score / total,
		confidence: conf / total,
		...(hasValue ? { value: value / total, base: base / total } : {})
	};
}
