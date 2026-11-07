import type { Cartographic, Viewer } from 'cesium';
import { NORDIC_BOX } from '../geo/regions.ts';
import type { CesiumModule } from './cesium.ts';

/** Street level inside Finland/Sweden. */
export const NORDIC_MIN_HEIGHT = 300;
/** Allow detailed exploration worldwide; Nordic simulation remains finer. */
export const WORLD_MIN_HEIGHT = 300;
/** Width (degrees) of the band outside the box over which the limit ramps up. */
const RAMP_DEG = 2.5;

const smoothstep = (t: number) => {
	const x = Math.min(1, Math.max(0, t));
	return x * x * (3 - 2 * x);
};

/** Minimum camera height above the surface at a lon/lat (degrees). */
export function minHeightAt(lon: number, lat: number): number {
	const [w, s, e, n] = NORDIC_BOX;
	const dLon = Math.max(0, w - lon, lon - e) * Math.cos((lat * Math.PI) / 180);
	const dLat = Math.max(0, s - lat, lat - n);
	const t = smoothstep(Math.hypot(dLon, dLat) / RAMP_DEG);
	// Interpolate in log space so the limit rises evenly from 300 m worldwide.
	return Math.exp(Math.log(NORDIC_MIN_HEIGHT) + t * Math.log(WORLD_MIN_HEIGHT / NORDIC_MIN_HEIGHT));
}

interface ZoomClampOptions {
	/** Height of the rendered surface (terrain or 3D tiles) below the camera. */
	surfaceHeight: (position: Cartographic) => number | undefined;
	/** Skip corrections while a scripted camera flight is running. */
	isFlying: () => boolean;
}

/**
 * Keeps the camera above the location-dependent minimum height. The zoom limit is
 * updated every frame, and if panning carries the camera into a stricter zone it is
 * eased upwards (exponentially, frame-rate independent) instead of snapping, so there's no jitter.
 */
export function installZoomClamp(C: CesiumModule, viewer: Viewer, opts: ZoomClampOptions) {
	const { scene, camera } = viewer;
	const ctrl = scene.screenSpaceCameraController;
	const up = new C.Cartesian3();
	let surface = 0;
	let lastSample = -Infinity;
	let lastFrame = performance.now();

	const onPreUpdate = () => {
		const carto = camera.positionCartographic;
		const now = performance.now();
		const dt = Math.min(0.25, (now - lastFrame) / 1000);
		lastFrame = now;
		if (now - lastSample > 250) {
			surface = opts.surfaceHeight(carto) ?? 0;
			lastSample = now;
		}

		const min = minHeightAt(C.Math.toDegrees(carto.longitude), C.Math.toDegrees(carto.latitude));
		ctrl.minimumZoomDistance = min;

		const above = carto.height - surface;
		if (opts.isFlying() || above >= min - 0.5) return;
		const gap = min - above;
		scene.globe.ellipsoid.geodeticSurfaceNormal(camera.positionWC, up);
		// Close ~95% of the gap per half second, independent of frame rate.
		const step = gap * (1 - Math.exp(-6 * dt));
		camera.move(up, Math.max(step, Math.min(gap, 2)));
		scene.requestRender(); // keep easing in request-render mode
	};

	scene.preUpdate.addEventListener(onPreUpdate);
	return () => scene.preUpdate.removeEventListener(onPreUpdate);
}
