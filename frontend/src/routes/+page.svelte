<script lang="ts">
	import 'cesium/Build/Cesium/Widgets/widgets.css';
	import { onMount } from 'svelte';
	import { dev } from '$app/env';
	import { PUBLIC_CESIUM_ION_TOKEN, PUBLIC_GOOGLE_MAPS_API_KEY, PUBLIC_NLS_API_KEY } from '$app/env/public';
	import { createGlobe, type Globe } from '#lib/globe/viewer.ts';
	import { startDrawing, type DrawingSession } from '#lib/drawing/index.ts';
	import Toolbar from '#lib/ui/Toolbar.svelte';
	import Hud from '#lib/ui/Hud.svelte';
	import TilesToggle from '#lib/ui/TilesToggle.svelte';
	import SidePanel from '#lib/ui/SidePanel.svelte';
	import { panelOpen } from '#lib/ui/panel.ts';
	import WeatherPanel from '#lib/weather/WeatherPanel.svelte';

	let container: HTMLDivElement;
	let credits: HTMLDivElement;
	let globe = $state.raw<Globe | null>(null);
	let drawing = $state<DrawingSession | null>(null);
	let failure = $state<string | null>(null);

	onMount(() => {
		let disposed = false;
		createGlobe(container, credits, {
			ionToken: PUBLIC_CESIUM_ION_TOKEN,
			googleKey: PUBLIC_GOOGLE_MAPS_API_KEY,
			nlsKey: PUBLIC_NLS_API_KEY
		})
			.then((g) => {
				if (disposed) return g.destroy();
				globe = g;
				// Handy for debugging in the browser console during development.
				if (dev) Object.assign(window, { __globe: g });
				drawing = startDrawing(g);
			})
			.catch((e) => {
				console.error(e);
				failure = e instanceof Error ? e.message : String(e);
			});

		// Developer shortcut until the side panel has content: "]" toggles it.
		const onKey = (e: KeyboardEvent) => {
			if (e.key === ']' && !(e.target instanceof HTMLInputElement)) panelOpen.update((v) => !v);
		};
		window.addEventListener('keydown', onKey);

		return () => {
			disposed = true;
			window.removeEventListener('keydown', onKey);
			drawing?.destroy();
			globe?.destroy();
		};
	});
</script>

<svelte:head>
	<title>BlueSky · Nordic globe</title>
</svelte:head>

<div class="app">
	<main class="stage">
		<div class="globe" bind:this={container}></div>

		<div class="top-left">
			<Toolbar
				onUndo={() => drawing?.undo()}
				onClear={() => drawing?.clear()}
				onExport={() => drawing?.exportGeoJSON()}
			/>
		</div>
		<div class="top-right">
			<TilesToggle onToggle={(on) => globe?.setTilesEnabled(on)} />
		</div>
		<div class="bottom-left"><Hud /></div>
		{#if globe}<WeatherPanel {globe} />{/if}
		<div class="credits" bind:this={credits}></div>

		{#if !globe}
			<div class="status">{failure ? `Globe failed to load: ${failure}` : 'Loading globe…'}</div>
		{/if}
	</main>

	<SidePanel />
</div>

<style>
	.app {
		position: fixed;
		inset: 0;
		display: flex;
		background: #000;
	}
	.stage {
		position: relative;
		flex: 1 1 auto;
		min-width: 0;
		overflow: hidden;
	}
	.globe {
		position: absolute;
		inset: 0;
	}
	.top-left {
		position: absolute;
		top: 16px;
		left: 16px;
		right: 200px;
		pointer-events: none;
	}
	.top-left > :global(*) {
		pointer-events: auto;
		width: max-content;
		max-width: 100%;
	}
	.top-right {
		position: absolute;
		top: 16px;
		right: 16px;
	}
	.bottom-left {
		position: absolute;
		left: 16px;
		bottom: 16px;
	}
	.status {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		color: var(--text-dim);
		font-size: 14px;
		pointer-events: none;
	}

	/* Required attributions (Cesium, Google, NLS): visible but quiet, bottom-right. */
	.credits {
		position: absolute;
		right: 12px;
		bottom: 8px;
		max-width: min(60%, 640px);
		text-align: right;
		font-size: 10px;
		line-height: 1.4;
		color: rgba(255, 255, 255, 0.6);
		opacity: 0.75;
	}
	.credits :global(.cesium-widget-credits) {
		position: static;
		display: block;
		font-size: inherit;
		color: inherit;
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.9);
	}
	.credits :global(.cesium-credit-logoContainer) {
		display: inline-block;
		vertical-align: middle;
	}
	.credits :global(.cesium-credit-logoContainer img) {
		height: 16px;
		width: auto;
	}
	.credits :global(.cesium-credit-textContainer) {
		display: inline;
	}
	.credits :global(.cesium-credit-expand-link) {
		color: rgba(255, 255, 255, 0.75);
		text-decoration: underline;
	}
	.credits :global(a) {
		color: inherit;
	}

	@media (max-width: 720px) {
		.top-left {
			right: 16px;
		}
		.top-right {
			top: auto;
			bottom: 16px;
		}
		.credits {
			max-width: calc(100% - 24px);
			bottom: 8px;
			top: auto;
		}
	}
</style>
