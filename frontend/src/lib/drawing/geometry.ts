import type { Position } from 'geojson';
import { toValidPolygon } from '../geo/turf.ts';
import type { ShapeFeature, ShapeMode } from './types.ts';

export interface ScreenPoint {
	x: number;
	y: number;
}

/** Freehand input is sampled at most once per this many screen pixels. */
export const FREEHAND_SAMPLE_PX = 4;
/** Douglas–Peucker tolerance for freehand strokes, in screen pixels. */
export const FREEHAND_TOLERANCE_PX = 1.5;

export const screenDistance = (a: ScreenPoint, b: ScreenPoint) => Math.hypot(a.x - b.x, a.y - b.y);

function segmentDistance(p: ScreenPoint, a: ScreenPoint, b: ScreenPoint) {
	const dx = b.x - a.x;
	const dy = b.y - a.y;
	const len2 = dx * dx + dy * dy;
	if (len2 === 0) return screenDistance(p, a);
	const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2));
	return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** Douglas–Peucker simplification; returns the indices of the points to keep. */
export function douglasPeucker(points: ScreenPoint[], tolerance: number): number[] {
	if (points.length <= 2) return points.map((_, i) => i);
	const keep = new Uint8Array(points.length);
	keep[0] = keep[points.length - 1] = 1;
	const stack: [number, number][] = [[0, points.length - 1]];
	while (stack.length) {
		const [start, end] = stack.pop()!;
		let maxDist = 0;
		let index = -1;
		for (let i = start + 1; i < end; i++) {
			const d = segmentDistance(points[i], points[start], points[end]);
			if (d > maxDist) {
				maxDist = d;
				index = i;
			}
		}
		if (index !== -1 && maxDist > tolerance) {
			keep[index] = 1;
			stack.push([start, index], [index, end]);
		}
	}
	return [...keep.keys()].filter((i) => keep[i]);
}

/** Builds a shape Feature from lon/lat points, or null if the shape is degenerate. */
export function buildShape(points: Position[], mode: ShapeMode): ShapeFeature | null {
	const geometry = toValidPolygon(points);
	if (!geometry) return null;
	return {
		type: 'Feature',
		geometry,
		properties: { id: crypto.randomUUID(), createdAt: new Date().toISOString(), mode }
	};
}
