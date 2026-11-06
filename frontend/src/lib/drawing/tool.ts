import type { Cartesian3, Entity, Viewer } from 'cesium';
import type { Position } from 'geojson';
import type { Unsubscriber } from 'svelte/store';
import type { CesiumModule } from '../globe/cesium.ts';
import { setCameraRotation } from '../globe/controls.ts';
import {
	FREEHAND_SAMPLE_PX,
	FREEHAND_TOLERANCE_PX,
	douglasPeucker,
	screenDistance,
	type ScreenPoint
} from './geometry.ts';
import { activeMode, drawMode } from './store.ts';
import type { DrawMode, ShapeMode } from './types.ts';

export const DRAW_COLOR = '#e53935';

/** Pointer travel (px) below which a press counts as a click rather than a drag. */
const CLICK_PX = 5;
/** Clicking within this distance (px) of the first vertex closes the polygon. */
const CLOSE_PX = 10;
const DOUBLE_CLICK_MS = 350;

interface Sample {
	screen: ScreenPoint;
	world: Cartesian3;
	lonLat: Position;
}

export interface DrawingToolOptions {
	/** Whether to pick on rendered geometry (3D tiles) instead of the ellipsoid. */
	pickOnTiles: () => boolean;
	onShape: (points: Position[], mode: ShapeMode) => void;
	/** Navigate-mode click: the shape id under the cursor, or null. */
	onSelect: (shapeId: string | null) => void;
	/** Delete/Backspace when no polygon is being drawn. */
	onDelete: () => void;
}

const isTyping = (e: KeyboardEvent) =>
	e.target instanceof HTMLElement && (e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName));

/**
 * Freehand (lasso) and click-to-place polygon drawing on the Cesium canvas.
 * Uses DOM pointer events so Shift+drag can be handled independently of Cesium's
 * modifier-specific input handlers.
 */
export class DrawingTool {
	private canvas: HTMLCanvasElement;
	private mode: DrawMode = 'navigate';
	private shiftHeld = false;
	private stroke: Sample[] | null = null;
	private vertices: Sample[] = [];
	private cursor: Cartesian3 | null = null;
	private press: (ScreenPoint & { id: number }) | null = null;
	private lastClick: (ScreenPoint & { t: number }) | null = null;
	private livePositions: Cartesian3[] = [];
	private liveLine: Entity;
	private unsubscribe: Unsubscriber;

	constructor(
		private C: CesiumModule,
		private viewer: Viewer,
		private opts: DrawingToolOptions
	) {
		this.canvas = viewer.scene.canvas;
		const red = C.Color.fromCssColorString(DRAW_COLOR);
		this.liveLine = viewer.entities.add({
			show: false,
			polyline: {
				positions: new C.CallbackProperty(() => this.livePositions, false),
				width: 2.5,
				arcType: C.ArcType.NONE,
				material: red,
				depthFailMaterial: red.withAlpha(0.8)
			}
		});

		this.canvas.addEventListener('pointerdown', this.onPointerDown);
		this.canvas.addEventListener('pointermove', this.onPointerMove);
		this.canvas.addEventListener('pointerup', this.onPointerUp);
		this.canvas.addEventListener('pointercancel', this.cancel);
		window.addEventListener('keydown', this.onKeyDown);
		window.addEventListener('keyup', this.onKeyUp);
		window.addEventListener('blur', this.onBlur);

		this.unsubscribe = drawMode.subscribe((mode) => {
			if (mode !== 'polygon') this.vertices = [];
			this.mode = mode;
			this.refresh();
		});
	}

	/** Undo while a polygon is in progress removes its last vertex. Returns true if handled. */
	undoVertex(): boolean {
		if (!this.vertices.length) return false;
		this.vertices.pop();
		this.refresh();
		return true;
	}

	destroy() {
		this.unsubscribe();
		this.canvas.removeEventListener('pointerdown', this.onPointerDown);
		this.canvas.removeEventListener('pointermove', this.onPointerMove);
		this.canvas.removeEventListener('pointerup', this.onPointerUp);
		this.canvas.removeEventListener('pointercancel', this.cancel);
		window.removeEventListener('keydown', this.onKeyDown);
		window.removeEventListener('keyup', this.onKeyUp);
		window.removeEventListener('blur', this.onBlur);
		if (!this.viewer.isDestroyed()) {
			this.viewer.entities.remove(this.liveLine);
			setCameraRotation(this.viewer, true);
		}
	}

	private get effectiveMode(): DrawMode {
		if (this.stroke) return 'freehand';
		if (this.shiftHeld && !this.vertices.length) return 'freehand';
		return this.mode;
	}

	/** Re-derives camera inputs, cursor, live line and the activeMode store from state. */
	private refresh() {
		const mode = this.effectiveMode;
		const drawing = mode === 'freehand' || (mode === 'polygon' && this.vertices.length > 0);
		setCameraRotation(this.viewer, !drawing);
		this.canvas.style.cursor = mode === 'navigate' ? '' : 'crosshair';
		activeMode.set(mode);

		if (this.stroke) {
			this.livePositions = this.stroke.map((s) => s.world);
		} else if (this.vertices.length) {
			this.livePositions = this.vertices.map((s) => s.world);
			if (this.cursor) this.livePositions.push(this.cursor);
		} else {
			this.livePositions = [];
		}
		this.liveLine.show = this.livePositions.length >= 2;
	}

	private screenPoint(e: PointerEvent): ScreenPoint {
		const rect = this.canvas.getBoundingClientRect();
		return { x: e.clientX - rect.left, y: e.clientY - rect.top };
	}

	/** Surface point under a screen position: 3D tiles first, then the ellipsoid. Height is dropped. */
	private pick(screen: ScreenPoint): Sample | null {
		const { C, viewer } = this;
		const { scene, camera } = viewer;
		const p = new C.Cartesian2(screen.x, screen.y);
		let world: Cartesian3 | undefined;
		if (this.opts.pickOnTiles() && scene.pickPositionSupported) world = scene.pickPosition(p);
		world ??= camera.pickEllipsoid(p, scene.globe.ellipsoid);
		if (!world) return null;
		const carto = C.Cartographic.fromCartesian(world);
		if (!carto) return null;
		return {
			screen,
			world,
			lonLat: [C.Math.toDegrees(carto.longitude), C.Math.toDegrees(carto.latitude)]
		};
	}

	private onPointerDown = (e: PointerEvent) => {
		if (e.button !== 0) return;
		const screen = this.screenPoint(e);
		this.press = { ...screen, id: e.pointerId };
		if (this.effectiveMode === 'freehand') {
			this.canvas.setPointerCapture(e.pointerId);
			const s = this.pick(screen);
			this.stroke = s ? [s] : [];
			this.refresh();
		}
	};

	private onPointerMove = (e: PointerEvent) => {
		const screen = this.screenPoint(e);
		if (this.stroke) {
			const last = this.stroke.at(-1);
			if (last && screenDistance(last.screen, screen) < FREEHAND_SAMPLE_PX) return;
			const s = this.pick(screen);
			if (s) this.stroke.push(s);
			this.refresh();
		} else if (this.mode === 'polygon' && this.vertices.length) {
			this.cursor = this.pick(screen)?.world ?? null;
			this.refresh();
		}
	};

	private onPointerUp = (e: PointerEvent) => {
		if (e.button !== 0) return;
		const screen = this.screenPoint(e);
		const press = this.press;
		this.press = null;

		if (this.stroke) {
			this.finishStroke();
			return;
		}
		if (!press || screenDistance(press, screen) > CLICK_PX) return; // a camera drag

		if (this.effectiveMode === 'polygon') this.polygonClick(screen);
		else if (this.effectiveMode === 'navigate') this.selectAt(screen);
	};

	private finishStroke() {
		const stroke = this.stroke ?? [];
		this.stroke = null;
		this.refresh();
		const keep = douglasPeucker(
			stroke.map((s) => s.screen),
			FREEHAND_TOLERANCE_PX
		);
		const points = keep.map((i) => stroke[i].lonLat);
		if (points.length >= 3) this.opts.onShape(points, 'freehand');
	}

	private polygonClick(screen: ScreenPoint) {
		const now = performance.now();
		const n = this.vertices.length;

		if (n >= 3) {
			const first = this.C.SceneTransforms.worldToWindowCoordinates(this.viewer.scene, this.vertices[0].world);
			if (first && screenDistance(first, screen) <= CLOSE_PX) return this.finishPolygon();
		}
		// Second click of a double-click: close instead of adding a duplicate vertex.
		const last = this.lastClick;
		if (n && last && now - last.t < DOUBLE_CLICK_MS && screenDistance(last, screen) <= CLICK_PX) {
			this.lastClick = null;
			if (n >= 3) this.finishPolygon();
			return;
		}

		const s = this.pick(screen);
		if (!s) return;
		this.vertices.push(s);
		this.lastClick = { ...screen, t: now };
		this.refresh();
	}

	private finishPolygon() {
		const points = this.vertices.map((v) => v.lonLat);
		this.vertices = [];
		this.cursor = null;
		this.refresh();
		if (points.length >= 3) this.opts.onShape(points, 'polygon');
	}

	private selectAt(screen: ScreenPoint) {
		const picked = this.viewer.scene.pick(new this.C.Cartesian2(screen.x, screen.y));
		const entityId = picked?.id instanceof this.C.Entity ? picked.id.id : undefined;
		const match = typeof entityId === 'string' ? /^shape(?:-outline)?:(.+)$/.exec(entityId) : null;
		this.opts.onSelect(match ? match[1] : null);
	}

	private cancel = () => {
		this.stroke = null;
		this.vertices = [];
		this.cursor = null;
		this.press = null;
		this.refresh();
	};

	private onKeyDown = (e: KeyboardEvent) => {
		if (isTyping(e)) return;
		if (e.key === 'Shift' && !this.shiftHeld) {
			this.shiftHeld = true;
			this.refresh();
		} else if (e.key === 'Escape') {
			this.cancel();
		} else if (e.key === 'Enter' && this.vertices.length >= 3) {
			this.finishPolygon();
		} else if (e.key === 'Delete' || e.key === 'Backspace') {
			e.preventDefault();
			if (!this.undoVertex()) this.opts.onDelete();
		}
	};

	private onKeyUp = (e: KeyboardEvent) => {
		if (e.key === 'Shift') {
			this.shiftHeld = false;
			this.refresh();
		}
	};

	private onBlur = () => {
		this.shiftHeld = false;
		if (this.stroke) this.finishStroke();
		else this.refresh();
	};
}
