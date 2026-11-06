<script lang="ts">
	import type { Snippet } from 'svelte';
	import { panelOpen } from './panel.ts';

	/** Slot for the future "Problems / Effects / Solutions / Impact" panel. */
	let { children }: { children?: Snippet } = $props();
</script>

<aside class="panel" class:open={$panelOpen} aria-hidden={!$panelOpen} inert={!$panelOpen}>
	<div class="inner">
		{@render children?.()}
	</div>
</aside>

<style>
	.panel {
		flex: 0 0 auto;
		width: 0;
		overflow: hidden;
		background: #0d121c;
		border-left: 1px solid var(--panel-border);
		transition: width 220ms ease;
	}
	.panel.open {
		width: min(400px, 100vw);
	}
	.inner {
		width: min(400px, 100vw);
		height: 100%;
		overflow-y: auto;
	}
</style>
