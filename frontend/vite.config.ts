import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { viteStaticCopy } from 'vite-plugin-static-copy';

// CesiumJS loads web workers, textures and widget CSS at runtime from CESIUM_BASE_URL.
// These folders are served/copied to /cesium, see src/lib/globe/cesium.ts.
const cesiumSource = 'node_modules/cesium/Build/Cesium';
const cesiumAssets = ['Workers', 'Assets', 'Widgets', 'ThirdParty'];

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		}),
		viteStaticCopy({
			targets: cesiumAssets.map((dir) => ({
				src: `${cesiumSource}/${dir}/**/*`,
				dest: `cesium/${dir}`,
				rename: { stripBase: 5 }
			}))
		})
	]
});
