<script lang="ts">
	import type { Globe } from '../globe/viewer.ts';
	import PolicyPanel from '../policy/PolicyPanel.svelte';
	import LensPanel from '../lens/LensPanel.svelte';
	import { selectedShape } from '../drawing/store.ts';

	let { globe }: { globe: Globe } = $props();
	let tab = $state<'scenario' | 'area'>('scenario');
</script>

<div class="tabs" role="tablist">
	<button role="tab" aria-selected={tab === 'scenario'} class:on={tab === 'scenario'} onclick={() => (tab = 'scenario')}>Scenario</button>
	<button role="tab" aria-selected={tab === 'area'} class:on={tab === 'area'} onclick={() => (tab = 'area')}>
		Area report{#if $selectedShape}<i></i>{/if}
	</button>
</div>
<!-- Both stay mounted so their globe layers persist; only one is visible. -->
<div hidden={tab !== 'scenario'}><PolicyPanel {globe} /></div>
<div hidden={tab !== 'area'}><LensPanel {globe} /></div>

<style>
	.tabs {
		position: sticky;
		top: 0;
		z-index: 1;
		display: flex;
		gap: 4px;
		padding: 10px 18px 0;
		background: #0d121c;
		border-bottom: 1px solid var(--panel-border);
	}
	.tabs button {
		position: relative;
		padding: 8px 12px;
		border: 0;
		border-bottom: 2px solid transparent;
		background: none;
		color: var(--text-dim);
		font-size: 12px;
		cursor: pointer;
	}
	.tabs button.on {
		color: var(--text);
		border-bottom-color: #cfeb9b;
	}
	.tabs i {
		position: absolute;
		top: 6px;
		right: 2px;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #e53935;
	}
</style>
