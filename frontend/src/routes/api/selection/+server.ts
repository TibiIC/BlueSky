import { json } from '@sveltejs/kit';
import { analyseSelection, selectionInput, selectionPolygons } from '#lib/geo/selection.ts';
import { lensReport } from '#lib/lens/report.server.ts';
import type { RequestHandler } from './$types';

/**
 * Receives a drawn area (GeoJSON Feature or FeatureCollection of Polygons) and
 * replies with { id, bbox, areaKm2, centroid, countries }.
 * `lens` adds the Climate Lens report: contract parcels, peat, catchments, climate
 * indicators by scenario and actions, computed from the Apetit package data.
 */
export const POST: RequestHandler = async ({ request, fetch }) => {
	let body: unknown;
	try {
		body = await request.json();
	} catch {
		return json({ error: 'Request body must be JSON' }, { status: 400 });
	}

	const parsed = selectionInput.safeParse(body);
	if (!parsed.success) {
		return json(
			{
				error: 'Expected a GeoJSON Feature or FeatureCollection of Polygons with lon/lat coordinates',
				issues: parsed.error.issues.map((i) => ({ path: i.path.join('.'), message: i.message }))
			},
			{ status: 400 }
		);
	}

	return json({ ...analyseSelection(parsed.data), lens: await lensReport(selectionPolygons(parsed.data), fetch) });
};
