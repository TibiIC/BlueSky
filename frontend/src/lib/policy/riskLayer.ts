import type { Primitive } from 'cesium';
import type { Globe } from '../globe/viewer.ts';
import { cellRisk, riskColor, type RiskId, type Warming } from './engine.ts';
import type { GridCell } from './data.ts';

const HALF = 0.125; // climate cells are 0.25° squares centred on their coordinates

/**
 * Red-to-green squares for the climate cells over Apetit's sourcing regions. The 84 cells are
 * rebuilt as one small primitive per change, which is simpler and cheaper than it sounds.
 */
export function attachRiskLayer(globe: Globe, cells: GridCell[], warming: Warming) {
	const { C, viewer } = globe;
	let primitive: Primitive | null = null;
	let visible = true;

	function clear() {
		if (primitive && !viewer.isDestroyed()) viewer.scene.primitives.remove(primitive);
		primitive = null;
	}

	function update(risk: RiskId, gwl: number) {
		clear();
		if (!visible || viewer.isDestroyed()) return viewer.scene.requestRender();
		const instances = cells
			.filter((c) => warming.cells[c.id])
			.map((c) => {
				const r = cellRisk(risk, warming.cells[c.id], gwl, warming);
				const [red, green, blue] = riskColor(r.score);
				return new C.GeometryInstance({
					id: c.id,
					geometry: new C.RectangleGeometry({
						rectangle: C.Rectangle.fromDegrees(c.lon - HALF, c.lat - HALF, c.lon + HALF, c.lat + HALF),
						height: 25,
						vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT
					}),
					attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(C.Color.fromBytes(red, green, blue, 135)) }
				});
			});
		primitive = viewer.scene.primitives.add(
			new C.Primitive({
				geometryInstances: instances,
				appearance: new C.PerInstanceColorAppearance({ translucent: true, flat: true }),
				asynchronous: false,
				allowPicking: false
			})
		);
		viewer.scene.requestRender();
	}

	return {
		update,
		setVisible(show: boolean) {
			visible = show;
			if (!show) {
				clear();
				viewer.scene.requestRender();
			}
		},
		destroy: clear
	};
}
