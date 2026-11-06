import type { Feature, FeatureCollection, Polygon } from 'geojson';
import type { SelectionResult } from '../geo/selection.ts';

export type DrawMode = 'navigate' | 'freehand' | 'polygon';
export type ShapeMode = Exclude<DrawMode, 'navigate'>;

export interface ShapeProperties {
	id: string;
	createdAt: string;
	mode: ShapeMode;
}

export type ShapeFeature = Feature<Polygon, ShapeProperties>;
export type ShapeCollection = FeatureCollection<Polygon, ShapeProperties>;

export type AnalysisState =
	| { status: 'pending' }
	| { status: 'done'; result: SelectionResult }
	| { status: 'error'; message: string };
