import type { ColorMaterialProperty, Entity, Viewer } from 'cesium';
import { get } from 'svelte/store';
import type { CesiumModule } from '../globe/cesium.ts';
import { selectedId, shapes } from './store.ts';
import { DRAW_COLOR } from './tool.ts';
import type { ShapeFeature } from './types.ts';

interface ShapeEntities {
	fill: Entity;
	outline: Entity;
	fillMaterial: ColorMaterialProperty;
	outlineMaterial: ColorMaterialProperty;
}

/** Mirrors the `shapes` store as red polygons draped on the globe and 3D tiles. */
export class ShapeLayer {
	private entities = new Map<string, ShapeEntities>();
	private unsubscribers: (() => void)[];

	constructor(
		private C: CesiumModule,
		private viewer: Viewer
	) {
		this.unsubscribers = [
			shapes.subscribe((fc) => this.sync(fc.features)),
			selectedId.subscribe(() => this.restyle())
		];
	}

	destroy() {
		this.unsubscribers.forEach((u) => u());
		if (this.viewer.isDestroyed()) return;
		for (const e of this.entities.values()) {
			this.viewer.entities.remove(e.fill);
			this.viewer.entities.remove(e.outline);
		}
	}

	private sync(features: ShapeFeature[]) {
		const ids = new Set(features.map((f) => f.properties.id));
		for (const [id, e] of this.entities) {
			if (ids.has(id)) continue;
			this.viewer.entities.remove(e.fill);
			this.viewer.entities.remove(e.outline);
			this.entities.delete(id);
		}
		for (const f of features) if (!this.entities.has(f.properties.id)) this.add(f);
		this.restyle();
	}

	private add(feature: ShapeFeature) {
		const { C } = this;
		const id = feature.properties.id;
		const ring = feature.geometry.coordinates[0];
		const flat = ring.slice(0, -1).flatMap(([lon, lat]) => [lon, lat]);
		const fillMaterial = new C.ColorMaterialProperty();
		const outlineMaterial = new C.ColorMaterialProperty();

		const fill = this.viewer.entities.add({
			id: `shape:${id}`,
			polygon: {
				hierarchy: C.Cartesian3.fromDegreesArray(flat),
				material: fillMaterial,
				classificationType: C.ClassificationType.BOTH
			}
		});
		const outline = this.viewer.entities.add({
			id: `shape-outline:${id}`,
			polyline: {
				positions: C.Cartesian3.fromDegreesArray(ring.flatMap(([lon, lat]) => [lon, lat])),
				width: 2.5,
				clampToGround: true,
				material: outlineMaterial,
				classificationType: C.ClassificationType.BOTH
			}
		});
		this.entities.set(id, { fill, outline, fillMaterial, outlineMaterial });
	}

	private restyle() {
		const { C } = this;
		const selected = get(selectedId);
		const red = C.Color.fromCssColorString(DRAW_COLOR);
		const highlight = C.Color.fromCssColorString('#ff8a80');
		for (const [id, e] of this.entities) {
			const isSelected = id === selected;
			e.fillMaterial.color = new C.ConstantProperty(red.withAlpha(isSelected ? 0.42 : 0.25));
			e.outlineMaterial.color = new C.ConstantProperty(isSelected ? highlight : red);
		}
	}
}
