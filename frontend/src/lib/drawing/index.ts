import type { Globe } from '../globe/viewer.ts';
import { analyseShape } from './api.ts';
import { buildShape } from './geometry.ts';
import { ShapeLayer } from './render.ts';
import { addShape, clearShapes, removeShape, selectedId, shapes, undoShapes } from './store.ts';
import { DrawingTool } from './tool.ts';
import { get } from 'svelte/store';

export interface DrawingSession {
	undo: () => void;
	clear: () => void;
	exportGeoJSON: () => void;
	destroy: () => void;
}

/** Wires the drawing tool, shape rendering, store and backend together on a globe. */
export function startDrawing(globe: Globe): DrawingSession {
	const layer = new ShapeLayer(globe.C, globe.viewer);
	const tool = new DrawingTool(globe.C, globe.viewer, {
		pickOnTiles: globe.tilesEnabled,
		onShape: (points, mode) => {
			const feature = buildShape(points, mode);
			if (!feature) return;
			addShape(feature);
			selectedId.set(feature.properties.id);
			analyseShape(feature);
		},
		onSelect: (id) => selectedId.set(id),
		onDelete: () => {
			const id = get(selectedId);
			if (id) removeShape(id);
		}
	});

	return {
		undo: () => tool.undoVertex() || undoShapes(),
		clear: clearShapes,
		exportGeoJSON: () => {
			const blob = new Blob([JSON.stringify(get(shapes), null, 2)], { type: 'application/geo+json' });
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = `selection-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.geojson`;
			a.click();
			setTimeout(() => URL.revokeObjectURL(a.href), 1000);
		},
		destroy: () => {
			tool.destroy();
			layer.destroy();
		}
	};
}
