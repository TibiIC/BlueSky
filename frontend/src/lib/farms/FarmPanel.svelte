<script lang="ts">
	import { untrack } from 'svelte';
	import type { Globe } from '../globe/viewer.ts';
	import type { Frame } from '../weather/terra.ts';
	import {
		attachFarms, APETIT_CROPS, CROP_COLORS, CROP_LABELS, REGION_LABELS, SEASONS, SOIL_COLORS, bioRgb, stressRgb,
		type FarmLayer, type FarmStatus
	} from './farms.ts';

	let { globe, regional }: { globe: Globe; regional?: Frame } = $props();
	let status = $state<FarmStatus>({ loaded: false, layer: 'off', shown: 0, total: 0, peat: 0, peatMisreported: 0, peatHa: 0 });
	let layer = $state<FarmLayer>('off');
	let crops = $state<Record<string, boolean>>(Object.fromEntries(Object.keys(CROP_COLORS).map(k => [k, true])));
	let regions = $state<Record<string, boolean>>(Object.fromEntries(Object.keys(REGION_LABELS).map(k => [k, true])));
	let peatOnly = $state(false);
	let speed = $state(5);
	let api: ReturnType<typeof attachFarms> | undefined;

	$effect(() => { const g = globe; const a = untrack(() => attachFarms(g, s => (status = s))); api = a; return () => { a.destroy(); api = undefined; }; });
	$effect(() => { const f = regional; untrack(() => api?.updateLive(f)); });

	const layers: [FarmLayer, string][] = [['off', 'Off'], ['crop', 'Crops 2026 (synthetic)'], ['soil', 'Soil class'], ['peat', 'Peat'], ['bio', 'Microbiome proxy'], ['stress_live', 'Timeline stress'], ['stress_replay', 'Season replay']];
	function chooseLayer(l: FarmLayer) { layer = l; if (l === 'stress_replay') api?.playSeason('2018'); else api?.setLayer(l); }
	function applyFilter() {
		api?.setFilter({ crops: new Set(Object.keys(crops).filter(k => crops[k])), regions: new Set(Object.keys(regions).filter(k => regions[k])), peatOnly });
	}
	function onlyApetit() { for (const k of Object.keys(crops)) crops[k] = APETIT_CROPS.includes(k); applyFilter(); }
	function allCrops() { for (const k of Object.keys(crops)) crops[k] = true; applyFilter(); }
	const rgb = (c: [number, number, number]) => `rgb(${c.join(',')})`;
	const pct = (v: number) => `${v.toFixed(0)}%`;
	const stats = $derived(layer==='stress_replay'?status.replay?.stats:layer==='stress_live'?status.live?.stats:undefined);
</script>

<div class="farms">
	<strong>APETIT SYNTHETIC FIELDS · {status.total ? status.total.toLocaleString() : '…'} PARCELS</strong>
	{#if status.error}<p class="error">{status.error}</p>{/if}
	<p class="note proxy">Synthetic challenge parcels and weather—not real grower locations or measured impacts. Parcel dots represent centroids, not field boundaries.</p>
	<div class="chips">
		{#each layers as [key, title]}<button class:chosen={layer === key} disabled={!status.loaded && key !== 'off'} onclick={() => chooseLayer(key)}>{title}</button>{/each}
	</div>

	{#if layer !== 'off'}
		<div class="buttons"><button onclick={() => api?.flyTo('FI_SW')}>Fly to Säkylä</button><button onclick={() => api?.flyTo('SE_SKANE')}>Fly to Skåne</button></div>

		{#if layer === 'crop'}
			<div class="legend">{#each Object.entries(CROP_COLORS) as [k, c]}<label class="check"><input type="checkbox" bind:checked={crops[k]} onchange={applyFilter} /><i style={`background:${c}`}></i>{CROP_LABELS[k]}</label>{/each}</div>
			<div class="buttons small"><button class="secondary" onclick={onlyApetit}>Apetit crops only</button><button class="secondary" onclick={allCrops}>Full rotation</button></div>
		{:else if layer === 'soil'}
			<div class="legend">{#each Object.entries(SOIL_COLORS) as [k, c]}<span><i style={`background:${c}`}></i>{k.replace('_', ' ')}</span>{/each}</div>
			<p class="note">Soil-map class per parcel. Drives the root-zone water capacity in the crop physics (sand 60 mm … organic 200 mm).</p>
		{:else if layer === 'peat'}
			<div class="legend"><span><i style="background:#ff3b30"></i>Map/report mismatch</span><span><i style="background:#ff9f0a"></i>Peat</span><span><i style="background:#9aa5a8"></i>Mineral</span></div>
			<div class="kpi"><span><b>{status.peat}</b> peat parcels · {status.peatHa.toFixed(0)} ha</span><span><b class="warn">{status.peatMisreported}</b> with a map/report mismatch</span><span>≈ <b>{(status.peatHa * 29 / 1000).toFixed(1)} kt CO₂/yr</b> illustrative scenario: all drained under annual crops</span></div>
			<p class="note">{status.notes?.peat}</p>
		{:else if layer === 'bio'}
			<div class="ramp" style={`background:linear-gradient(90deg,${rgb(bioRgb(0))},${rgb(bioRgb(0.4))},${rgb(bioRgb(0.8))})`}></div><div class="range"><span>low</span><span>high potential</span></div>
			<p class="note proxy">MICROBIOME DIVERSITY PROXY — NOT MEASURED. No microbial sampling or sequencing data is supplied. This management-based habitat indicator cannot establish microbial diversity. {status.notes?.biodiversity}</p>
		{:else}
			<div class="ramp" style={`background:linear-gradient(90deg,${rgb(stressRgb(0))},${rgb(stressRgb(0.5))},${rgb(stressRgb(1))})`}></div><div class="range"><span>no water stress</span><span>wilting point</span></div>
			{#if layer === 'stress_replay'}
				<div class="mode-tabs">{#each SEASONS as [key, title]}<button class:chosen={status.replay?.key === key} onclick={() => api?.playSeason(key)}>{title}</button>{/each}</div>
				{#if status.replay}
					<div class="clock"><button class="play" onclick={() => api?.togglePlay()}>{status.replay.playing ? '❚❚' : '▶'}</button><b>{status.replay.date}</b><input type="range" min="0" max={status.replay.days - 1} step="0.25" value={status.replay.day} oninput={e => api?.seek(Number((e.target as HTMLInputElement).value))} /></div>
					<label class="speed">Speed <input type="range" min="1" max="20" bind:value={speed} oninput={() => api?.setSpeed(speed)} /><span>{speed} d/s</span></label>
				{/if}
				<p class="note">{status.replay?.label}. FAO-56 bucket per climate cell and soil class, with generic crop calendars and synthetic challenge weather. The 2026 crop map is reused for each replay year.</p>
			{:else}
				<p class="note">Each parcel samples the running TERRA physics (crop_stress = 1 − Ks) every frame. {status.live ? `Sim time ${status.live.simTime.slice(0, 16).replace('T', ' ')} UTC.` : 'Waiting for the live feed…'} Generic regional water availability is sampled, not crop-specific field physics.</p>
			{/if}
			{#if stats}
				<div class="kpi">{#each Object.entries(stats) as [r, s]}<span>{REGION_LABELS[r] ?? r}<b class:warn={s.stressedPct > 30}>{pct(s.stressedPct)} of crop area stressed</b></span>{/each}</div>
				<p class="note">Selected synthetic Apetit crop parcels, area-weighted; stressed = 1 − Ks ≥ 0.5.</p>
			{/if}
		{/if}

		<div class="filters">
			{#each Object.entries(REGION_LABELS) as [k, title]}<label class="check"><input type="checkbox" bind:checked={regions[k]} onchange={applyFilter} />{title}</label>{/each}
			<label class="check"><input type="checkbox" bind:checked={peatOnly} onchange={applyFilter} />Peat parcels only</label>
			<small>{status.shown.toLocaleString()} parcels shown</small>
		</div>

		{#if status.selected}
			{@const s = status.selected}
			<div class="card">
				<header><b>{s.id}</b><button class="x" aria-label="Close parcel" onclick={() => api?.clearSelection()}>×</button></header>
				<dl>
					<dt>Crop 2026</dt><dd>{CROP_LABELS[s.crop]}</dd>
					<dt>Area</dt><dd>{s.area.toFixed(2)} ha</dd>
					<dt>Soil</dt><dd>{s.soil.replace('_', ' ')} · clay {s.clay.toFixed(0)}% · {s.drainage.replace('_', ' ')}</dd>
					<dt>Peat</dt><dd class:warn={s.peatMisreported}>{s.peat ? (s.peatMisreported ? 'Soil map says organic; farm report says mineral' : 'Yes') : 'No'}</dd>
					<dt>Biodiversity proxy</dt><dd>{s.bio.toFixed(2)} · rotation {s.rotation.toFixed(2)} · catch crops {(s.catchShare * 100).toFixed(0)}%{s.organicFarm ? ' · organic' : ''}</dd>
					{#if s.stress !== null}<dt>Water stress now</dt><dd>{(s.stress * 100).toFixed(0)}%</dd>{/if}
					<dt>Farm</dt><dd>{s.farm} · {REGION_LABELS[s.region] ?? s.region}</dd>
				</dl>
			</div>
		{/if}
		<p class="note src">{status.notes?.source}</p>
	{/if}
</div>

<style>
	.farms { margin-top: 12px; padding: 10px; background: #12262e; border: 1px solid #37534c; border-radius: 5px; font-size: 10px; }
	.farms > strong { font-size: 9px; letter-spacing: 1px; color: #cfeb9b; }
	.chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 10px 0; }
	.chips button, .mode-tabs button { flex: 0 0 auto; background: #18313b; color: #a3b6b8; border: 1px solid #385158; border-radius: 4px; padding: 5px 7px; font-size: 10px; cursor: pointer; }
	.chips button.chosen, .mode-tabs button.chosen { background: #cfeb9b; color: #14251a; }
	.chips button:disabled { opacity: 0.4; cursor: wait; }
	.mode-tabs { display: flex; gap: 5px; margin: 10px 0; }
	.buttons { display: flex; gap: 6px; margin: 8px 0; }
	.buttons button { flex: 1; background: #cfeb9b; border: 0; border-radius: 4px; padding: 6px; color: #14251a; cursor: pointer; font-size: 10px; }
	.buttons .secondary { background: #18313b; color: #cfeb9b; border: 1px solid #385158; }
	.legend { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; margin: 8px 0; }
	.legend span, .check { display: flex; align-items: center; gap: 6px; margin: 0; justify-content: flex-start; font-size: 10px; color: #e3eee8; }
	i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; flex: none; }
	.ramp { height: 6px; margin-top: 10px; border-radius: 3px; }
	.range { display: flex; justify-content: space-between; margin-top: 4px; color: #a3b6b8; font-size: 9px; }
	.kpi { display: grid; gap: 6px; margin: 10px 0; }
	.kpi span { display: flex; justify-content: space-between; gap: 8px; color: #a3b6b8; }
	b { color: #d3ebba; font-weight: 600; }
	.warn { color: #ff8a80 !important; }
	.clock { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
	.clock b { font: 12px monospace; color: #fff; }
	.clock input { flex: 1; }
	.play { background: #cfeb9b; border: 0; border-radius: 4px; width: 30px; height: 24px; cursor: pointer; color: #14251a; }
	.speed { display: flex; align-items: center; gap: 8px; margin: 4px 0; color: #a3b6b8; }
	.speed input { flex: 1; }
	.filters { display: grid; gap: 4px; border-top: 1px solid #385158; margin-top: 10px; padding-top: 8px; }
	.filters small { color: #a3b6b8; font-size: 9px; }
	.card { margin-top: 10px; padding: 8px; background: #0e222b; border: 1px solid #385158; border-radius: 5px; }
	.card header { display: flex; justify-content: space-between; align-items: center; }
	.x { background: transparent; border: 0; color: #cfeb9b; font-size: 14px; cursor: pointer; }
	dl { margin: 6px 0 0; display: grid; grid-template-columns: auto 1fr; gap: 3px 8px; }
	dt { color: #a3b6b8; font-size: 9px; }
	dd { margin: 0; font-size: 10px; color: #e3eee8; }
	.note { font-size: 9px; line-height: 1.5; color: #a3b6b8; }
	.proxy { border-left: 2px solid #ffd60a; padding-left: 6px; }
	.src { font-size: 8px; opacity: 0.8; }
	.error { color: #edbb88; }
</style>
