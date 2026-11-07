import type { Cesium3DTileset, Viewer } from 'cesium';
import { FINLAND_BOX } from '../geo/regions.ts';
import type { CesiumModule } from './cesium.ts';
import { imageryState, tilesState } from './state.ts';

export interface ImageryKeys {
	ionToken?: string;
	googleKey?: string;
	nlsKey?: string;
}

const NLS_HOST = 'avoin-karttakuva.maanmittauslaitos.fi';

/**
 * Tier 1: world satellite imagery (Cesium ion, or bundled keyless Natural Earth II).
 * Tier 3: NLS Finland orthophoto, clipped to Finland.
 */
export async function addBaseImagery(C: CesiumModule, viewer: Viewer, keys: ImageryKeys) {
	const layers = viewer.imageryLayers;

	if (keys.ionToken) {
		// ion default world imagery (Bing Maps aerial)
		layers.add(C.ImageryLayer.fromWorldImagery({}));
	} else {
		console.warn(
			'[globe] PUBLIC_CESIUM_ION_TOKEN is not set: using keyless low-resolution Natural Earth II imagery. ' +
				'Add a Cesium ion token for global satellite imagery and 3D tiles.'
		);
		layers.add(
			C.ImageryLayer.fromProviderAsync(
				C.TileMapServiceImageryProvider.fromUrl(C.buildModuleUrl('Assets/Textures/NaturalEarthII'))
			)
		);
	}

 // Public MapServer endpoint supported by Cesium. Keep bundled Natural Earth underneath.
 // Service availability/terms can change; optional ion imagery remains supported.
 if (!keys.ionToken) {
  C.ArcGisMapServerImageryProvider.fromUrl('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer', { enablePickFeatures: false })
   .then(provider => {
    if (viewer.isDestroyed()) return;
    layers.addImageryProvider(provider, 1);
    imageryState.update(s => ({...s, world: 'esri'}));
   }).catch(error => console.warn('[globe] Esri imagery unavailable; retaining Natural Earth', error));
 }

	if (keys.nlsKey) {
		// The open NLS WMTS is meant for light use and rejects bursts with 503s:
		// cap parallel requests, request only inside Finland and only when zoomed in.
		C.RequestScheduler.requestsByServer[`${NLS_HOST}:443`] = 4;
		const rectangle = C.Rectangle.fromDegrees(...FINLAND_BOX);
		const provider = new C.WebMapTileServiceImageryProvider({
			url:
				`https://${NLS_HOST}/avoin/wmts/1.0.0/ortokuva/default/WGS84_Pseudo-Mercator/` +
				`{TileMatrix}/{TileRow}/{TileCol}.jpg?api-key=${encodeURIComponent(keys.nlsKey)}`,
			layer: 'ortokuva',
			style: 'default',
			format: 'image/jpeg',
			tileMatrixSetID: 'WGS84_Pseudo-Mercator',
			tilingScheme: new C.WebMercatorTilingScheme(),
			rectangle,
			maximumLevel: 18,
			credit: new C.Credit(
				'Orthophoto: © <a href="https://www.maanmittauslaitos.fi/en" target="_blank" rel="noopener">National Land Survey of Finland</a>, CC BY 4.0'
			)
		});
		layers.add(new C.ImageryLayer(provider, { rectangle, minimumTerrainLevel: 8 }));
	}

	imageryState.set({ world: keys.ionToken ? 'ion' : 'keyless', finlandOrthophoto: !!keys.nlsKey });
}

/**
 * Tier 2: Google Photorealistic 3D Tiles, via a Google key if set, otherwise via Cesium ion.
 * Resolves to null if neither key is available or loading fails.
 */
export async function addGoogleTiles(C: CesiumModule, viewer: Viewer, keys: ImageryKeys): Promise<Cesium3DTileset | null> {
	if (!keys.googleKey && !keys.ionToken) {
		tilesState.set({
			status: 'unavailable',
			enabled: false,
			reason: 'Set PUBLIC_CESIUM_ION_TOKEN or PUBLIC_GOOGLE_MAPS_API_KEY to enable 3D cities'
		});
		return null;
	}
	try {
		if (keys.googleKey) C.GoogleMaps.defaultApiKey = keys.googleKey;
		// No geocoder is used anywhere in the app, which satisfies Google's "Google geocoder only" rule.
		const tileset = await C.createGooglePhotorealistic3DTileset(
			{ key: keys.googleKey, onlyUsingWithGoogleGeocoder: true },
			{
				showCreditsOnScreen: true,
				enableCollision: true,
				// 24 instead of 12: about a quarter of the tile requests and decode work, still sharp at city zoom.
				maximumScreenSpaceError: 24,
				dynamicScreenSpaceError: true,
				foveatedScreenSpaceError: true,
				preloadFlightDestinations: false
			}
		);
		viewer.scene.primitives.add(tileset);
		return tileset;
	} catch (error) {
		console.error('[globe] Failed to load Google Photorealistic 3D Tiles', error);
		tilesState.set({ status: 'unavailable', enabled: false, reason: 'Google 3D tiles failed to load (see console)' });
		return null;
	}
}
