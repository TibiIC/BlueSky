<script lang="ts">
	import type { Snippet } from 'svelte';
	import { panelOpen } from './panel.ts';

	/** Right-hand panel. Collapses to a thin rail (not to nothing) so it can always be reopened. */
	let { children }: { children?: Snippet } = $props();
</script>

<aside class="panel" class:open={$panelOpen}>
	{#if !$panelOpen}
		<button class="rail" aria-label="Open panel" title="Open panel (])" onclick={() => panelOpen.set(true)}>
			<span>‹</span><small>Scenario · Area · Weather</small>
		</button>
	{/if}
	<div class="inner" hidden={!$panelOpen}>
		{@render children?.()}
	</div>
</aside>

<style>
	.panel {
		flex: 0 0 auto;
		width: 36px;
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
	.rail {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
		width: 100%;
		height: 100%;
		padding: 14px 0;
		border: 0;
		background: none;
		color: #cfeb9b;
		cursor: pointer;
	}
	.rail span {
		font-size: 18px;
	}
	.rail small {
		writing-mode: vertical-rl;
		font-size: 11px;
		letter-spacing: 0.08em;
		color: var(--text-dim);
	}
</style>
