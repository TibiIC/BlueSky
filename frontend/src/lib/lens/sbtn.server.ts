import type { Polygon } from 'geojson';
import { booleanIntersects } from '@turf/turf';
import { loadLensData, parcelsInside } from './report.server.ts';
import type { SbtnCatchment, SbtnInput } from './sbtn.ts';

/**
 * The SBTN screening review's input for a drawn area, in the shape the
 * Climate_Lens_SBTN_Lite notebook page reads: parcels whose centroid lies in the
 * area, catchments the area crosses, and catchments those parcels drain to.
 */
export async function sbtnInput(
	polygons: Polygon[],
	selection: { globeId: string; name: string },
	fetcher: typeof fetch
): Promise<SbtnInput | null> {
	const loaded = await loadLensData(fetcher);
	if (!loaded) return null;
	const { parcels: P, catchments } = loaded.data;

	const idx = parcelsInside(P, polygons);
	const matches: SbtnInput['matches'] = idx.map((i) => [
		P.id[i],
		P.catchment[i],
		P.area[i],
		P.buffer[i],
		P.drainage[i],
		P.soil[i],
		P.distWater[i],
		P.planCrop[i]
	]);

	const record = ({ properties: c }: (typeof catchments.features)[number]): SbtnCatchment => ({
		catchment_id: c.id,
		region: c.region,
		receiving_water_type: c.water,
		ecological_status_class: c.status,
		catchment_area_km2: c.areaKm2,
		load: c.load ? { year: String(c.load.year), total_p_load_kg: c.load.pKg, total_n_load_kg: c.load.nKg } : null
	});
	const linked = new Set(idx.map((i) => P.catchment[i]));

	return {
		...selection,
		selected: polygons.map((p) => p.coordinates),
		matches,
		crossed: catchments.features.filter((f) => polygons.some((p) => booleanIntersects(p, f.geometry))).map(record),
		related: catchments.features.filter((f) => linked.has(f.properties.id)).map(record)
	};
}
