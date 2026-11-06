import type { Viewer } from 'cesium';
import type { CesiumModule } from './cesium.ts';

/** Left-drag rotates, wheel/pinch zooms, right-drag / Ctrl+left-drag / middle-drag tilts. */
export function configureCameraControls(C: CesiumModule, viewer: Viewer) {
	const ctrl = viewer.scene.screenSpaceCameraController;
	const { CameraEventType, KeyboardEventModifier } = C;

	ctrl.rotateEventTypes = CameraEventType.LEFT_DRAG;
	ctrl.translateEventTypes = CameraEventType.LEFT_DRAG;
	ctrl.zoomEventTypes = [CameraEventType.WHEEL, CameraEventType.PINCH];
	ctrl.tiltEventTypes = [
		CameraEventType.RIGHT_DRAG,
		CameraEventType.MIDDLE_DRAG,
		CameraEventType.PINCH,
		{ eventType: CameraEventType.LEFT_DRAG, modifier: KeyboardEventModifier.CTRL },
		{ eventType: CameraEventType.RIGHT_DRAG, modifier: KeyboardEventModifier.CTRL }
	];
	// Shift is reserved for "hold to draw freehand", so free-look is disabled.
	ctrl.enableLook = false;

	ctrl.inertiaSpin = 0.9;
	ctrl.inertiaTranslate = 0.9;
	ctrl.inertiaZoom = 0.8;
	ctrl.maximumZoomDistance = 40_000_000;
	ctrl.enableCollisionDetection = true;
}

/** Turns camera rotation/pan/tilt off while drawing; zoom stays available. */
export function setCameraRotation(viewer: Viewer, enabled: boolean) {
	const ctrl = viewer.scene.screenSpaceCameraController;
	ctrl.enableRotate = enabled;
	ctrl.enableTranslate = enabled;
	ctrl.enableTilt = enabled;
}
