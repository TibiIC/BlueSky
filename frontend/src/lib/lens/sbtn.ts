import type { Position } from 'geojson';
import { PUBLIC_SBTN_URL } from '$app/env/public';
import type { ShapeFeature } from '../drawing/types.ts';

export interface SbtnCatchment {
	catchment_id: string;
	region: string;
	receiving_water_type: string;
	ecological_status_class: string;
	catchment_area_km2: number;
	/** Phosphorus sensitivity of the receiving water (1 = typical, higher = more sensitive). */
	p_sensitivity: number;
	monitored: boolean;
	load: { year: string; total_p_load_kg: number; total_n_load_kg: number } | null;
}

/** What the SBTN review page (sbtn/) reads. Field names follow the Climate_Lens_SBTN_Lite notebook. */
export interface SbtnInput {
	globeId: string;
	name: string;
	/** Drawn polygons' coordinates (outer ring first). */
	selected: Position[][][];
	/**
	 * [parcel, catchment, whole-parcel ha, buffer strip, drainage, soil, metres to water, planned crop,
	 *  soil P test mg/L (null if none), peat t CO₂e/yr, farm, Apetit contract crop, centroid lon, centroid lat]
	 * The notebook page reads the first eight; the report backend reads them all.
	 */
	matches: [string, string, number, boolean, string, string, number, string, number | null, number, string, boolean, number, number][];
	/** Catchments the drawn area crosses. */
	crossed: SbtnCatchment[];
	/** Catchments the matched parcels drain to. */
	related: SbtnCatchment[];
}

/**
 * Opens the SBTN review in a new tab and hands it this shape's parcels.
 *
 * The review runs on its own origin, so the selection travels by postMessage: the page
 * says `sbtn:ready` to its opener and gets `sbtn:input` back. Reloading the review tab
 * asks again, for as long as the tab is open.
 */
export function openSbtnReview(shape: ShapeFeature): boolean {
	const url = new URL(PUBLIC_SBTN_URL);
	// Must run synchronously in the click handler, or popup blockers stop it.
	const review = window.open(url, '_blank');
	if (!review) return false;

	const name = `selection-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.geojson`;
	const input = fetch('/api/sbtn', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ name, selection: shape })
	}).then(async (res) => {
		const body = await res.json();
		if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
		return body as SbtnInput;
	});

	const onMessage = (e: MessageEvent) => {
		if (e.source !== review || e.origin !== url.origin || e.data?.type !== 'sbtn:ready') return;
		input.then(
			(data) => review.postMessage({ type: 'sbtn:input', data }, url.origin),
			(err) => review.postMessage({ type: 'sbtn:error', message: err instanceof Error ? err.message : String(err) }, url.origin)
		);
	};
	window.addEventListener('message', onMessage);
	const watch = setInterval(() => {
		if (review.closed) {
			window.removeEventListener('message', onMessage);
			clearInterval(watch);
		}
	}, 2000);
	return true;
}
