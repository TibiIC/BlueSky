<script lang="ts">
	import { areaKm2, centroidOf, type LonLat } from '../geo/turf.ts';
	import { analyses, selectedShape, shapes } from '../drawing/store.ts';

	const local = $derived(
		$selectedShape
			? { area: areaKm2($selectedShape.geometry), centroid: centroidOf($selectedShape.geometry) }
			: null
	);
	const server = $derived($selectedShape ? $analyses[$selectedShape.properties.id] : undefined);

	const fmtArea = (km2: number) =>
		km2 < 10
			? km2.toLocaleString('en-GB', { maximumFractionDigits: 3 })
			: km2.toLocaleString('en-GB', { maximumFractionDigits: 1 });
	const fmtCoord = ({ lat, lon }: LonLat) =>
		`${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? 'E' : 'W'}`;
</script>

<section class="hud" aria-live="polite">
	{#if $selectedShape && local}
		<header>
			<span class="swatch"></span>
			<strong>Selected area</strong>
			<span class="badge">{$selectedShape.properties.mode}</span>
		</header>
		<dl>
			<dt>Area</dt>
			<dd>{fmtArea(local.area)} km²</dd>
			<dt>Centroid</dt>
			<dd>{fmtCoord(local.centroid)}</dd>
		</dl>
		<div class="server">
			{#if !server || server.status === 'pending'}
				<span class="muted">Sending to /api/selection…</span>
			{:else if server.status === 'error'}
				<span class="error">Server error: {server.message}</span>
			{:else}
				<div class="server-title">Server reply</div>
				<dl>
					<dt>Area</dt>
					<dd>{fmtArea(server.result.areaKm2)} km²</dd>
					<dt>Centroid</dt>
					<dd>{fmtCoord(server.result.centroid)}</dd>
					<dt>Countries</dt>
					<dd>
						{#each server.result.countries as c (c)}<span class="chip">{c}</span>{:else}<span class="muted"
								>Outside Finland and Sweden</span
							>{/each}
					</dd>
					<dt>BBox</dt>
					<dd class="mono">{server.result.bbox.map((v) => v.toFixed(3)).join(', ')}</dd>
				</dl>
			{/if}
		</div>
		<footer>{$shapes.features.length} shape{$shapes.features.length === 1 ? '' : 's'} · Delete removes selection</footer>
	{:else}
		<p class="muted">
			{#if $shapes.features.length}
				Click a red shape to select it.
			{:else}
				Draw an area with <b>Freehand</b> (or hold <kbd>Shift</kbd> and drag) or <b>Polygon</b>.
			{/if}
		</p>
	{/if}
</section>

<style>
	.hud {
		width: 300px;
		max-width: calc(100vw - 32px);
		padding: 12px 14px;
		background: var(--panel-bg);
		border: 1px solid var(--panel-border);
		border-radius: 12px;
		backdrop-filter: blur(12px);
		box-shadow: var(--panel-shadow);
		font-size: 13px;
	}
	header {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 8px;
	}
	.swatch {
		width: 12px;
		height: 12px;
		border-radius: 3px;
		background: rgba(229, 57, 53, 0.35);
		border: 2px solid #e53935;
	}
	.badge {
		margin-left: auto;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-faint);
	}
	dl {
		display: grid;
		grid-template-columns: 72px 1fr;
		gap: 4px 8px;
		margin: 0;
	}
	dt {
		color: var(--text-faint);
	}
	dd {
		margin: 0;
		font-variant-numeric: tabular-nums;
	}
	.server {
		margin-top: 10px;
		padding-top: 10px;
		border-top: 1px solid var(--panel-border);
	}
	.server-title {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #81c784;
		margin-bottom: 6px;
	}
	.chip {
		display: inline-block;
		padding: 1px 8px;
		margin-right: 4px;
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.1);
		font-size: 12px;
	}
	.mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 11px;
	}
	.muted {
		color: var(--text-dim);
		margin: 0;
	}
	.error {
		color: #ff8a80;
	}
	footer {
		margin-top: 10px;
		font-size: 11px;
		color: var(--text-faint);
	}
	kbd {
		padding: 0 4px;
		border: 1px solid var(--panel-border);
		border-radius: 4px;
		font: inherit;
		font-size: 11px;
	}
</style>
