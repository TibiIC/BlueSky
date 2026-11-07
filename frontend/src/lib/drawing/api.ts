import type { SelectionReply } from '../geo/selection.ts';
import { analyses } from './store.ts';
import type { ShapeFeature } from './types.ts';

/** Sends a finished shape to the backend and records the reply in the `analyses` store. */
export async function analyseShape(feature: ShapeFeature) {
	const id = feature.properties.id;
	analyses.update((a) => ({ ...a, [id]: { status: 'pending' } }));
	try {
		const res = await fetch('/api/selection', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(feature)
		});
		const body = await res.json();
		if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
		analyses.update((a) => ({ ...a, [id]: { status: 'done', result: body as SelectionReply } }));
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		analyses.update((a) => ({ ...a, [id]: { status: 'error', message } }));
	}
}
