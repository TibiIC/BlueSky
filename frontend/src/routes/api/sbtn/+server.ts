import { json } from '@sveltejs/kit';
import { z } from 'zod';
import { analyseSelection, selectionInput, selectionPolygons } from '#lib/geo/selection.ts';
import { sbtnInput } from '#lib/lens/sbtn.server.ts';
import type { RequestHandler } from './$types';

const body = z.object({
	name: z.string().max(200).default('Globe selection'),
	selection: selectionInput
});

/**
 * Receives { name, selection } where selection is a drawn area (as for /api/selection)
 * and replies with the SBTN review's input: matched parcels and catchments.
 */
export const POST: RequestHandler = async ({ request, fetch }) => {
	let raw: unknown;
	try {
		raw = await request.json();
	} catch {
		return json({ error: 'Request body must be JSON' }, { status: 400 });
	}

	const parsed = body.safeParse(raw);
	if (!parsed.success) {
		return json(
			{
				error: 'Expected { name, selection } with a GeoJSON Feature or FeatureCollection of Polygons',
				issues: parsed.error.issues.map((i) => ({ path: i.path.join('.'), message: i.message }))
			},
			{ status: 400 }
		);
	}

	const { name, selection } = parsed.data;
	const input = await sbtnInput(selectionPolygons(selection), { globeId: analyseSelection(selection).id, name }, fetch);
	if (!input) return json({ error: 'Climate Lens data not built. Run: python3 lens/build_data.py' }, { status: 503 });
	return json(input);
};
