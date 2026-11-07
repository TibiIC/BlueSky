import type { Feature, FeatureCollection, Polygon } from 'geojson';
import type { SelectionReply } from '../geo/selection.ts';

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
	| { status: 'done'; result: SelectionReply }
	| { status: 'error'; message: string };
