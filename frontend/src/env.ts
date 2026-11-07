import { defineEnvVars } from '@sveltejs/kit/env';

/** Optional public key: empty or missing values become `undefined`. */
const optionalKey = (description: string) => ({
	public: true,
	description,
	schema: (value: string | undefined) => value?.trim() || undefined
});

export const variables = defineEnvVars({
	PUBLIC_CESIUM_ION_TOKEN: optionalKey(
		'Cesium ion access token. Unlocks ion world imagery and Google Photorealistic 3D Tiles via ion.'
	),
	PUBLIC_GOOGLE_MAPS_API_KEY: optionalKey(
		'Google Map Tiles API key. Loads Google Photorealistic 3D Tiles directly from Google instead of via ion.'
	),
	PUBLIC_NLS_API_KEY: optionalKey(
		'National Land Survey of Finland (Maanmittauslaitos) API key. Adds the Finnish orthophoto layer.'
	),
	PUBLIC_SBTN_URL: {
		public: true,
		description: 'Where the SBTN screening review (sbtn/run.sh) is served. The Lens panel opens it with the selected parcels.',
		schema: (value: string | undefined) => value?.trim() || 'http://localhost:8300'
	}
});
