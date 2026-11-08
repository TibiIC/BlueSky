import adapter from '@sveltejs/adapter-node';
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

			// adapter-node: a standalone Node server (frontend/build), run on our Vultr VM behind Caddy (deploy/).
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
