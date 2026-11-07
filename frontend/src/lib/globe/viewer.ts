import type { Cesium3DTileset, Viewer } from 'cesium';
import { NORDIC_CENTER } from '../geo/regions.ts';
import { addCountryBorders } from './borders.ts';
import { loadCesium, type CesiumModule } from './cesium.ts';
import { configureCameraControls } from './controls.ts';
import { addBaseImagery, addGoogleTiles, type ImageryKeys } from './imagery.ts';
import { addCityLabels } from './labels.ts';
import { tilesState } from './state.ts';
import { installZoomClamp } from './zoomClamp.ts';

export interface Globe {
	C: CesiumModule;
	viewer: Viewer;
	/** True when Google 3D tiles are shown (and the plain globe surface is hidden). */
	tilesEnabled: () => boolean;
	setTilesEnabled: (on: boolean) => void;
	destroy: () => void;
}

export async function createGlobe(
	container: HTMLElement,
	creditContainer: HTMLElement,
	keys: ImageryKeys
): Promise<Globe> {
	const C = await loadCesium();
	if (keys.ionToken) C.Ion.defaultAccessToken = keys.ionToken;

	const viewer = new C.Viewer(container, {
		baseLayer: false,
		animation: false,
		timeline: false,
		baseLayerPicker: false,
		geocoder: false,
		homeButton: false,
		navigationHelpButton: false,
		fullscreenButton: false,
		sceneModePicker: false,
		infoBox: false,
		selectionIndicator: false,
		vrButton: false,
		creditContainer,
		// Performance: CSS-pixel resolution (halves the work on HiDPI screens) and no MSAA;
		// cheap FXAA smooths edges instead. Integrated GPUs were dropping to single-digit fps.
		useBrowserRecommendedResolution: true,
		msaaSamples: 1,
		// Render only when something changes (camera, tiles, data, explicit requestRender),
		// instead of 60 times a second while idle.
		requestRenderMode: true,
		maximumRenderTimeChange: Infinity
	});
	const { scene, camera } = viewer;

	// Star skybox and atmosphere on, no sun-based night side (Finnish winters are dark enough).
	if (scene.skyAtmosphere) scene.skyAtmosphere.show = true;
	scene.globe.showGroundAtmosphere = true;
	scene.globe.enableLighting = false;
	scene.globe.baseColor = C.Color.fromCssColorString('#0a1626');
	scene.backgroundColor = C.Color.BLACK;
	scene.fog.enabled = true;
	scene.globe.depthTestAgainstTerrain = false;
	if (scene.skyBox) scene.skyBox.show = true;
	scene.postProcessStages.fxaa.enabled = true;

	// In request-render mode, pointer and wheel input must trigger a frame so live drawing
	// previews (CallbackProperty) and hover feedback update.
	const kick = () => scene.requestRender();
	for (const ev of ['pointermove', 'pointerdown', 'pointerup', 'wheel'] as const)
		scene.canvas.addEventListener(ev, kick, { passive: true });
	window.addEventListener('keydown', kick);
	// ...and so do loading tiles and new imagery layers, otherwise the first view can stay black.
	scene.globe.tileLoadProgressEvent.addEventListener(kick);
	scene.imageryLayers.layerAdded.addEventListener(kick);

	// The viewer's default double-click zooms to entities; we use double-click to close polygons.
	viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
	viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_CLICK);

	configureCameraControls(C, viewer);
	await addBaseImagery(C, viewer, keys);
	addCityLabels(C, viewer);
	addCountryBorders(C, viewer).catch((e) => console.warn('[globe] borders:', e));

	let tileset: Cesium3DTileset | null = null;
	const setTilesEnabled = (on: boolean) => {
		if (!tileset) return;
		tileset.show = on;
		// Google tiles cover the whole planet; Cesium recommends no globe underneath them.
		scene.globe.show = !on;
		tilesState.set({ status: 'ready', enabled: on });
		scene.requestRender();
	};

	let flying = false;
	const removeClamp = installZoomClamp(C, viewer, {
		surfaceHeight: (carto) =>
			tileset?.show ? tileset.getHeight(carto, scene) : scene.globe.getHeight(carto),
		isFlying: () => flying
	});

	// Start on the whole Earth. Weather panel provides an explicit Nordic flight.
	camera.setView({ destination: C.Cartesian3.fromDegrees(NORDIC_CENTER.lon, 25, 24_000_000) });

	addGoogleTiles(C, viewer, keys).then((ts) => {
		if (viewer.isDestroyed()) return;
		tileset = ts;
		// Off by default: Google 3D tiles were the main source of main-thread stalls (~280 ms/s).
		// The "3D cities" toggle turns them on for close-up views.
		if (ts) setTilesEnabled(false);
	});

	scene.requestRender();
	return {
		C,
		viewer,
		tilesEnabled: () => !!tileset?.show,
		setTilesEnabled,
		destroy: () => {
			removeClamp();
			window.removeEventListener('keydown', kick);
			if (!viewer.isDestroyed()) viewer.destroy();
		}
	};
}
