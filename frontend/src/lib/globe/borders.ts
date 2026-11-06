import type { FeatureCollection, LineString, MultiLineString } from 'geojson';
import type { GroundPolylinePrimitive, Viewer } from 'cesium';
import { BORDERS_URL } from '../geo/regions.ts';
import type { CesiumModule } from './cesium.ts';

/**
 * Thin country borders from Natural Earth 1:50m land boundaries, draped on the
 * globe and on 3D tiles. All lines go into one primitive to keep draw calls low.
 */
export async function addCountryBorders(C: CesiumModule, viewer: Viewer): Promise<GroundPolylinePrimitive> {
	const res = await fetch(BORDERS_URL);
	if (!res.ok) throw new Error(`Failed to load borders (${res.status})`);
	const data = (await res.json()) as FeatureCollection<LineString | MultiLineString>;

	const instances = data.features.flatMap((f) => {
		const lines = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates;
		return lines
			.filter((line) => line.length >= 2)
			.map(
				(line) =>
					new C.GeometryInstance({
						geometry: new C.GroundPolylineGeometry({
							positions: C.Cartesian3.fromDegreesArray(line.flatMap(([lon, lat]) => [lon, lat])),
							width: 1.25
						})
					})
			);
	});

	const primitive = new C.GroundPolylinePrimitive({
		geometryInstances: instances,
		appearance: new C.PolylineMaterialAppearance({
			material: C.Material.fromType('Color', { color: C.Color.WHITE.withAlpha(0.42) })
		}),
		classificationType: C.ClassificationType.BOTH,
		allowPicking: false
	});
	return viewer.scene.groundPrimitives.add(primitive);
}
