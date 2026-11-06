import { derived, get, writable } from 'svelte/store';
import type { AnalysisState, DrawMode, ShapeCollection, ShapeFeature } from './types.ts';

/** All drawn shapes as a GeoJSON FeatureCollection. Panels subscribe to this. */
export const shapes = writable<ShapeCollection>({ type: 'FeatureCollection', features: [] });

/** Mode chosen in the toolbar. */
export const drawMode = writable<DrawMode>('navigate');
/** Mode actually in effect (holding Shift temporarily switches to freehand). */
export const activeMode = writable<DrawMode>('navigate');

export const selectedId = writable<string | null>(null);

export const selectedShape = derived([shapes, selectedId], ([$shapes, $id]) =>
	$id ? ($shapes.features.find((f) => f.properties.id === $id) ?? null) : null
);

/** Responses from POST /api/selection, keyed by shape id. */
export const analyses = writable<Record<string, AnalysisState>>({});

// Snapshots of the feature list before each change, for Undo.
const history: ShapeFeature[][] = [];

function commit(next: ShapeFeature[]) {
	history.push(get(shapes).features);
	if (history.length > 100) history.shift();
	shapes.set({ type: 'FeatureCollection', features: next });
	const id = get(selectedId);
	if (id && !next.some((f) => f.properties.id === id)) selectedId.set(null);
}

export function addShape(feature: ShapeFeature) {
	commit([...get(shapes).features, feature]);
}

export function removeShape(id: string) {
	const features = get(shapes).features;
	if (features.some((f) => f.properties.id === id)) commit(features.filter((f) => f.properties.id !== id));
}

export function clearShapes() {
	if (get(shapes).features.length) commit([]);
}

/** Reverts the last add/remove/clear. Returns false if there is nothing to undo. */
export function undoShapes(): boolean {
	const previous = history.pop();
	if (!previous) return false;
	shapes.set({ type: 'FeatureCollection', features: previous });
	const id = get(selectedId);
	if (id && !previous.some((f) => f.properties.id === id)) selectedId.set(null);
	return true;
}
