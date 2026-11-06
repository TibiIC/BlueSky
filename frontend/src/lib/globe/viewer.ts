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
		// Render at device pixel ratio for sharp imagery on HiDPI screens.
		useBrowserRecommendedResolution: false,
		msaaSamples: 4
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
	};

	let flying = false;
	const removeClamp = installZoomClamp(C, viewer, {
		surfaceHeight: (carto) =>
			tileset?.show ? tileset.getHeight(carto, scene) : scene.globe.getHeight(carto),
		isFlying: () => flying
	});

	// Start with the whole Earth, then ease to Finland and Sweden.
	camera.setView({ destination: C.Cartesian3.fromDegrees(NORDIC_CENTER.lon, 25, 24_000_000) });
	const fly = () => {
		flying = true;
		camera.flyToBoundingSphere(
			new C.BoundingSphere(C.Cartesian3.fromDegrees(NORDIC_CENTER.lon, NORDIC_CENTER.lat), 0),
			{
				offset: new C.HeadingPitchRange(0, C.Math.toRadians(-72), 3_300_000),
				duration: 4.5,
				easingFunction: C.EasingFunction.CUBIC_IN_OUT,
				complete: () => (flying = false),
				cancel: () => (flying = false)
			}
		);
	};
	const introTimer = setTimeout(fly, 1600);

	addGoogleTiles(C, viewer, keys).then((ts) => {
		if (viewer.isDestroyed()) return;
		tileset = ts;
		if (ts) setTilesEnabled(true);
	});

	return {
		C,
		viewer,
		tilesEnabled: () => !!tileset?.show,
		setTilesEnabled,
		destroy: () => {
			clearTimeout(introTimer);
			removeClamp();
			if (!viewer.isDestroyed()) viewer.destroy();
		}
	};
}
