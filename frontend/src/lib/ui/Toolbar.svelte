<script lang="ts">
	import { activeMode, drawMode, shapes } from '../drawing/store.ts';
	import type { DrawMode } from '../drawing/types.ts';
	import Icon from './Icon.svelte';

	let { onUndo, onClear, onExport }: { onUndo: () => void; onClear: () => void; onExport: () => void } =
		$props();

	const modes: { mode: DrawMode; label: string; hint: string }[] = [
		{ mode: 'navigate', label: 'Navigate', hint: 'Drag to rotate · right-drag or Ctrl-drag to tilt · hold Shift to draw' },
		{ mode: 'freehand', label: 'Freehand', hint: 'Press and drag to draw an area · release to close' },
		{ mode: 'polygon', label: 'Polygon', hint: 'Click to add points · double-click, Enter or click the first point to close · Esc cancels' }
	];

	const hint = $derived(modes.find((m) => m.mode === $activeMode)?.hint);
	const count = $derived($shapes.features.length);
</script>

<div class="toolbar" role="toolbar" aria-label="Drawing tools">
	<div class="group">
		{#each modes as m (m.mode)}
			<button
				class:active={$activeMode === m.mode}
				aria-pressed={$drawMode === m.mode}
				title={m.hint}
				onclick={() => drawMode.set(m.mode)}
			>
				<Icon name={m.mode} />
				<span>{m.label}</span>
			</button>
		{/each}
	</div>
	<div class="divider"></div>
	<div class="group">
		<button title="Undo (also removes the last polygon point while drawing)" onclick={onUndo}>
			<Icon name="undo" /><span>Undo</span>
		</button>
		<button title="Remove all shapes" onclick={onClear} disabled={!count}>
			<Icon name="trash" /><span>Clear all</span>
		</button>
		<button title="Download shapes as GeoJSON" onclick={onExport} disabled={!count}>
			<Icon name="download" /><span>Export GeoJSON</span>
		</button>
	</div>
</div>
{#if hint}<p class="hint">{hint}</p>{/if}

<style>
	.toolbar {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px;
		background: var(--panel-bg);
		border: 1px solid var(--panel-border);
		border-radius: 12px;
		backdrop-filter: blur(12px);
		box-shadow: var(--panel-shadow);
		flex-wrap: wrap;
	}
	.group {
		display: flex;
		gap: 2px;
	}
	.divider {
		width: 1px;
		align-self: stretch;
		background: var(--panel-border);
		margin: 4px 2px;
	}
	button {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 7px 10px;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--text-dim);
		font: inherit;
		font-size: 13px;
		cursor: pointer;
		transition:
			background 120ms,
			color 120ms;
	}
	button:hover:not(:disabled) {
		background: rgba(255, 255, 255, 0.07);
		color: var(--text);
	}
	button.active {
		background: rgba(229, 57, 53, 0.18);
		color: #ff8a80;
	}
	button:disabled {
		opacity: 0.38;
		cursor: default;
	}
	button:focus-visible {
		outline: 2px solid #ff8a80;
		outline-offset: 1px;
	}
	.hint {
		display: inline-block;
		margin: 8px 0 0;
		padding: 4px 10px;
		border-radius: 8px;
		background: rgba(12, 16, 26, 0.6);
		font-size: 12px;
		color: var(--text-dim);
	}
	@media (max-width: 720px) {
		button span {
			display: none;
		}
	}
</style>
