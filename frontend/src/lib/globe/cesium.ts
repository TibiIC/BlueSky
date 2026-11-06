export type CesiumModule = typeof import('cesium');

declare global {
	interface Window {
		CESIUM_BASE_URL?: string;
	}
}

let cesium: Promise<CesiumModule> | undefined;

/**
 * Loads CesiumJS in the browser only. CESIUM_BASE_URL must be set before the module
 * evaluates so workers and assets resolve to the folders copied by vite-plugin-static-copy.
 */
export function loadCesium(): Promise<CesiumModule> {
	window.CESIUM_BASE_URL = '/cesium/';
	cesium ??= import('cesium');
	return cesium;
}
