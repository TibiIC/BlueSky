import type { BBox, Polygon } from 'geojson';
import { z } from 'zod';
import type { LensResult } from '../lens/types.ts';
import { intersectingCountries } from './countries.ts';
import { areaKm2, bboxOf, centroidOf, type LonLat } from './turf.ts';

const MAX_VERTICES = 20_000;

const position = z.tuple([z.number().min(-180).max(180), z.number().min(-90).max(90)], z.number());

const linearRing = z
	.array(position)
	.min(4, 'a linear ring needs at least 4 positions')
	.refine((ring) => ring[0][0] === ring.at(-1)![0] && ring[0][1] === ring.at(-1)![1], {
		message: 'a linear ring must be closed (first position equals last)'
	});

const polygon = z.object({
	type: z.literal('Polygon'),
	coordinates: z
		.array(linearRing)
		.min(1)
		.refine((rings) => rings.reduce((n, r) => n + r.length, 0) <= MAX_VERTICES, {
			message: `polygon has more than ${MAX_VERTICES} vertices`
		})
});

const feature = z.object({
	type: z.literal('Feature'),
	id: z.union([z.string(), z.number()]).optional(),
	geometry: polygon,
	properties: z.record(z.string(), z.unknown()).nullable().optional()
});

const featureCollection = z.object({
	type: z.literal('FeatureCollection'),
	features: z.array(feature).min(1).max(200)
});

/** The polygons of a validated selection, for spatial queries. */
export function selectionPolygons(input: SelectionInput): Polygon[] {
	return input.type === 'Feature' ? [input.geometry] : input.features.map((f) => f.geometry);
}

/** Accepts a GeoJSON Feature or FeatureCollection whose geometries are all Polygons. */
export const selectionInput = z.discriminatedUnion('type', [feature, featureCollection]);
export type SelectionInput = z.infer<typeof selectionInput>;

export interface SelectionResult {
	id: string;
	bbox: BBox;
	areaKm2: number;
	centroid: LonLat;
	/** Countries the shape intersects, from Natural Earth borders, e.g. ["Finland"]. */
	countries: string[];
}

/** Server reply: geometry facts plus the Climate Lens report for the area. */
export type SelectionReply = (SelectionResult | SelectionCollectionResult) & { lens?: LensResult };

export interface SelectionCollectionResult extends SelectionResult {
	/** Per-feature results when a FeatureCollection was posted; top-level fields cover all features. */
	features: SelectionResult[];
}

function describe(id: string, geometry: Polygon): SelectionResult {
	return {
		id,
		bbox: bboxOf(geometry),
		areaKm2: Math.round(areaKm2(geometry) * 1000) / 1000,
		centroid: centroidOf(geometry),
		countries: intersectingCountries(geometry)
	};
}

function featureId(f: z.infer<typeof feature>): string {
	const propId = f.properties?.id;
	if (typeof propId === 'string' || typeof propId === 'number') return String(propId);
	if (f.id !== undefined) return String(f.id);
	return crypto.randomUUID();
}

export function analyseSelection(input: SelectionInput): SelectionResult | SelectionCollectionResult {
	if (input.type === 'Feature') return describe(featureId(input), input.geometry);

	const results = input.features.map((f) => describe(featureId(f), f.geometry));
	const boxes = results.map((r) => r.bbox);
	const totalArea = results.reduce((sum, r) => sum + r.areaKm2, 0);
	const weighted = (pick: (c: LonLat) => number) =>
		Math.round((results.reduce((s, r) => s + pick(r.centroid) * r.areaKm2, 0) / totalArea) * 1e6) / 1e6;
	return {
		id: crypto.randomUUID(),
		bbox: [
			Math.min(...boxes.map((b) => b[0])),
			Math.min(...boxes.map((b) => b[1])),
			Math.max(...boxes.map((b) => b[2])),
			Math.max(...boxes.map((b) => b[3]))
		],
		areaKm2: Math.round(totalArea * 1000) / 1000,
		centroid: { lon: weighted((c) => c.lon), lat: weighted((c) => c.lat) },
		countries: [...new Set(results.flatMap((r) => r.countries))],
		features: results
	};
}
