import type { BBox, Feature, Polygon, Position } from 'geojson';
import {
	area,
	bbox,
	booleanClockwise,
	centerOfMass,
	kinks,
	polygon as turfPolygon,
	unkinkPolygon
} from '@turf/turf';

/** Shapes smaller than this are treated as accidental clicks. */
export const MIN_AREA_M2 = 100;

export interface LonLat {
	lon: number;
	lat: number;
}

const round6 = (v: number) => Math.round(v * 1e6) / 1e6;

export function areaKm2(geometry: Polygon): number {
	return area(geometry) / 1e6;
}

/** Area-weighted centroid (better than a vertex average for dense freehand outlines). */
export function centroidOf(geometry: Polygon): LonLat {
	const [lon, lat] = centerOfMass(geometry).geometry.coordinates;
	return { lon: round6(lon), lat: round6(lat) };
}

export function bboxOf(geometry: Polygon): BBox {
	return bbox(geometry).map(round6) as BBox;
}

/**
 * Turn a list of lon/lat points into a valid RFC 7946 polygon: drops heights and
 * repeated points, closes the ring, resolves self-intersections (keeps the largest
 * loop) and orients the exterior ring counter-clockwise.
 * Returns null for degenerate input (< 3 distinct points or negligible area).
 */
export function toValidPolygon(points: Position[]): Polygon | null {
	const ring: Position[] = [];
	for (const [lon, lat] of points) {
		const p = [round6(lon), round6(lat)];
		const prev = ring.at(-1);
		if (!prev || prev[0] !== p[0] || prev[1] !== p[1]) ring.push(p);
	}
	if (ring.length > 1 && ring[0][0] === ring.at(-1)![0] && ring[0][1] === ring.at(-1)![1]) ring.pop();
	if (ring.length < 3) return null;
	ring.push([...ring[0]]);

	let poly: Feature<Polygon> = turfPolygon([ring]);
	if (kinks(poly).features.length > 0) {
		const parts = unkinkPolygon(poly).features;
		poly = parts.reduce((best, f) => (area(f) > area(best) ? f : best), parts[0]);
	}

	const exterior = poly.geometry.coordinates[0];
	if (exterior.length < 4 || area(poly) < MIN_AREA_M2) return null;
	if (booleanClockwise(exterior)) exterior.reverse();
	return { type: 'Polygon', coordinates: [exterior] };
}
