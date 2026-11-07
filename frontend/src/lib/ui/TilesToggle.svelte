<script lang="ts">
	import { imageryState, tilesState } from '../globe/state.ts';
	import Icon from './Icon.svelte';

	let { onToggle }: { onToggle: (on: boolean) => void } = $props();

	const layers = $derived(
		[
			$imageryState.world === 'ion' ? 'Cesium ion imagery' : $imageryState.world === 'esri' ? 'Esri world imagery' : $imageryState.world === 'keyless' ? 'Natural Earth fallback' : null,
			$imageryState.finlandOrthophoto ? 'NLS orthophoto' : null,
			$tilesState.status === 'ready' ? 'Google 3D Tiles' : null
		].filter(Boolean)
	);
	const label = $derived(
		$tilesState.status === 'loading' ? '3D cities…' : `3D cities ${$tilesState.enabled ? 'on' : 'off'}`
	);
</script>

<div class="tiles">
	<button
		class:on={$tilesState.enabled}
		disabled={$tilesState.status !== 'ready'}
		aria-pressed={$tilesState.enabled}
		title={$tilesState.reason ?? 'Google Photorealistic 3D Tiles'}
		onclick={() => onToggle(!$tilesState.enabled)}
	>
		<Icon name="cube" />
		<span>{label}</span>
	</button>
	{#if layers.length}<p>{layers.join(' · ')}</p>{/if}
	{#if $tilesState.status === 'unavailable' && $tilesState.reason}<p class="reason">{$tilesState.reason}</p>{/if}
</div>

<style>
	.tiles {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 6px;
	}
	button {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 8px 12px;
		border-radius: 10px;
		border: 1px solid var(--panel-border);
		background: var(--panel-bg);
		backdrop-filter: blur(12px);
		box-shadow: var(--panel-shadow);
		color: var(--text-dim);
		font: inherit;
		font-size: 13px;
		cursor: pointer;
	}
	button.on {
		color: var(--text);
		border-color: rgba(255, 255, 255, 0.22);
	}
	button:hover:not(:disabled) {
		color: var(--text);
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	p {
		margin: 0;
		padding: 3px 8px;
		border-radius: 6px;
		background: rgba(12, 16, 26, 0.6);
		font-size: 11px;
		color: var(--text-dim);
	}
	p.reason {
		max-width: 260px;
		text-align: right;
	}
</style>
