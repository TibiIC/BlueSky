import type { Entity, PointPrimitive } from 'cesium';
import type { FeatureCollection, Polygon } from 'geojson';
import { bbox, booleanPointInPolygon } from '@turf/turf';
import type { Globe } from '../globe/viewer.ts';

/** Water-status colours (WFD ecological status classes). */
export const STATUS_COLOR: Record<string, string> = {
	good: '#5fb3e6',
	moderate: '#e8d36b',
	poor: '#e8955a',
	bad: '#e0565b'
};
/** Soil-map colours; organic (peat) stands out. */
export const SOIL_COLOR: Record<string, string> = {
	clay: '#b9a07a',
	silt: '#c9c19a',
	fine_sand: '#d8cf9f',
	sand: '#efe3b0',
	organic: '#ff7a1a'
};

interface ParcelCols {
	id: string[];
	lon: number[];
	lat: number[];
	soil: string[];
}

export interface LensLayer {
	ready: Promise<boolean>;
	setCatchmentsVisible: (show: boolean) => void;
	setParcelsVisible: (show: boolean) => void;
	/** Enlarges the parcels whose centroid falls in the polygon; null clears. */
	highlight: (geometry: Polygon | null) => void;
	destroy: () => void;
}

/** Catchment outlines coloured by status and contract-parcel points coloured by soil. */
export function attachLensLayer(globe: Globe): LensLayer {
	const { C, viewer } = globe;
	let destroyed = false;
	const entities: Entity[] = [];
	const points = viewer.scene.primitives.add(new C.PointPrimitiveCollection());
	let parcelPoints: PointPrimitive[] = [];
	let parcels: ParcelCols | null = null;
	let highlighted: number[] = [];

	const near = new C.DistanceDisplayCondition(0, 900_000);
	const baseSize = (soil: string) => (soil === 'organic' ? 5 : 3);

	const ready = (async () => {
		try {
			const [cg, pc] = await Promise.all([
				fetch('/data/lens/catchments.geojson').then((r) => (r.ok ? r.json() : Promise.reject(r.status))),
				fetch('/data/lens/parcels.json').then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
			]);
			if (destroyed) return false;
			for (const f of (cg as FeatureCollection<Polygon, { id: string; status: string }>).features) {
				const color = C.Color.fromCssColorString(STATUS_COLOR[f.properties.status] ?? '#ffffff');
				const ring = f.geometry.coordinates[0].flat();
				// Outline only: draped fills and ground-clamped lines are expensive classification passes.
				// depthFailMaterial keeps the line visible when 3D tiles are on.
				entities.push(
					viewer.entities.add({
						name: `Catchment ${f.properties.id} · ${f.properties.status}`,
						polyline: {
							positions: C.Cartesian3.fromDegreesArrayHeights(ring.flatMap((v, i) => (i % 2 ? [v, 40] : [v]))),
							width: 1.5,
							material: color.withAlpha(0.8),
							depthFailMaterial: color.withAlpha(0.5)
						}
					})
				);
			}
			parcels = pc as ParcelCols;
			parcelPoints = parcels.id.map((_, i) =>
				points.add({
					position: C.Cartesian3.fromDegrees(parcels!.lon[i], parcels!.lat[i], 30),
					pixelSize: baseSize(parcels!.soil[i]),
					color: C.Color.fromCssColorString(SOIL_COLOR[parcels!.soil[i]] ?? '#ffffff').withAlpha(0.9),
					outlineColor: C.Color.BLACK.withAlpha(0.6),
					outlineWidth: 0.5,
					distanceDisplayCondition: near,
					// Draw above 3D tiles and terrain, which would otherwise bury points placed near the ellipsoid.
					disableDepthTestDistance: Number.POSITIVE_INFINITY
				})
			);
			viewer.scene.requestRender();
			return true;
		} catch (e) {
			console.warn('[lens] layer data unavailable (run python3 lens/build_data.py):', e);
			return false;
		}
	})();

	return {
		ready,
		setCatchmentsVisible: (show) => {
			entities.forEach((e) => (e.show = show));
			viewer.scene.requestRender();
		},
		setParcelsVisible: (show) => {
			points.show = show;
			viewer.scene.requestRender();
		},
		highlight(geometry) {
			for (const i of highlighted) {
				const p = parcelPoints[i];
				if (p) {
					p.pixelSize = baseSize(parcels!.soil[i]);
					p.outlineColor = C.Color.BLACK.withAlpha(0.6);
				}
			}
			highlighted = [];
			if (!geometry || !parcels) return;
			const [w, s, e, n] = bbox(geometry);
			for (let i = 0; i < parcels.id.length; i++) {
				const x = parcels.lon[i], y = parcels.lat[i];
				if (x < w || x > e || y < s || y > n || !booleanPointInPolygon([x, y], geometry)) continue;
				parcelPoints[i].pixelSize = baseSize(parcels.soil[i]) + 3;
				parcelPoints[i].outlineColor = C.Color.WHITE;
				highlighted.push(i);
			}
			viewer.scene.requestRender();
		},
		destroy() {
			destroyed = true;
			entities.forEach((e) => viewer.entities.remove(e));
			if (!viewer.isDestroyed()) viewer.scene.primitives.remove(points);
		}
	};
}
