<script lang="ts">
	import { untrack } from 'svelte';
	import type { Globe } from '../globe/viewer.ts';
	import { analyses, selectedShape } from '../drawing/store.ts';
	import { centroidOf } from '../geo/turf.ts';
	import { panelOpen, activeTab } from '../ui/panel.ts';
	import ReviewPanel from '../review/ReviewPanel.svelte';
	import { attachLensLayer, SOIL_COLOR, STATUS_COLOR, type LensLayer } from './layer.ts';
	import { terraNow, type TerraNow } from './terraNow.ts';
	import { openSbtnReview } from './sbtn.ts';
	import {
		DECADES,
		SCENARIOS,
		SCENARIO_LABEL,
		type ClimateIndicators,
		type Decade,
		type LensReport,
		type Scenario
	} from './types.ts';

	let { globe }: { globe: Globe } = $props();

	let layer: LensLayer | undefined;
	let showCatchments = $state(true);
	let showParcels = $state(true);
	let scenario = $state<Scenario>('ssp245');
	let decade = $state<Decade>('2050s');
	let now = $state<TerraNow | null | 'loading'>(null);
	let sbtnBlocked = $state(false);

	$effect(() => {
		const target = globe;
		const l = untrack(() => attachLensLayer(target));
		layer = l;
		return () => {
			l.destroy();
			layer = undefined;
		};
	});

	const analysis = $derived($selectedShape ? $analyses[$selectedShape.properties.id] : undefined);
	const lens = $derived(analysis?.status === 'done' ? analysis.result.lens : undefined);
	const report = $derived(lens?.available ? (lens as LensReport) : null);
	const hasParcels = $derived(!!report && report.area.parcels > 0);

	// Parcels and synthetic catchments step aside on the Weather tab, which has its own field and river layers.
	$effect(() => {
		const onWeather = $activeTab === 'weather';
		layer?.setCatchmentsVisible(showCatchments && !onWeather);
		layer?.setParcelsVisible(showParcels && !onWeather);
	});

	// Highlight the selected area's parcels and open the panel when a report arrives.
	$effect(() => {
		const shape = $selectedShape;
		layer?.highlight(shape ? shape.geometry : null);
	});
	let lastOpened: string | null = null;
	$effect(() => {
		const id = $selectedShape?.properties.id ?? null;
		if (id && report && id !== lastOpened) {
			lastOpened = id;
			panelOpen.set(true);
		}
	});

	// Live conditions from TERRA for the selected area's centroid.
	$effect(() => {
		const shape = $selectedShape;
		if (!shape || !hasParcels) {
			now = null;
			return;
		}
		const ctrl = new AbortController();
		now = 'loading';
		terraNow(centroidOf(shape.geometry), ctrl.signal).then((v) => {
			if (!ctrl.signal.aborted) now = v;
		});
		return () => ctrl.abort();
	});

	const CROP: Record<string, string> = {
		pea: 'Pea',
		carrot: 'Carrot',
		potato: 'Potato',
		spinach: 'Spinach',
		turnip_rape: 'Turnip rape',
		barley: 'Barley',
		oats: 'Oats',
		wheat: 'Wheat',
		grass_ley: 'Grass ley',
		fallow: 'Fallow'
	};
	const SEGMENT: Record<string, string> = { veg: 'vegetable', oil: 'oilseed', se_pea: 'Swedish pea' };
	const fmt = (v: number, nd = 0) => v.toLocaleString('en-GB', { maximumFractionDigits: nd, minimumFractionDigits: nd });
	const pct = (v: number) => `${Math.round(v * 100)} %`;
	const signed = (v: number, nd = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), nd)}`;

	interface Metric {
		key: keyof ClimateIndicators;
		label: string;
		unit: string;
		nd: number;
		/** +1 when higher is worse for crops, −1 when lower is worse. */
		bad: 1 | -1 | 0;
		asPct?: boolean;
	}
	const METRICS: Metric[] = [
		{ key: 'hotDaysJJ', label: 'Hot days in June–July (≥ 27 °C)', unit: 'days', nd: 1, bad: 1 },
		{ key: 'pHeatSeason', label: 'Seasons with ≥ 8 hot days', unit: '', nd: 0, bad: 1, asPct: true },
		{ key: 'waterBalanceMJJA', label: 'May–Aug water balance (rain − evaporation)', unit: 'mm', nd: 0, bad: -1 },
		{ key: 'tmeanMJJA', label: 'May–Aug mean temperature', unit: '°C', nd: 1, bad: 0 },
		{ key: 'gdd5', label: 'Growing degree days (> 5 °C)', unit: '°C·d', nd: 0, bad: 0 },
		{ key: 'heavyRainDaysJAS', label: 'Wet-harvest days, Jul–Sep (≥ 20 mm)', unit: 'days', nd: 1, bad: 1 },
		{ key: 'frostDaysMay', label: 'Late-frost days in May', unit: 'days', nd: 1, bad: 1 }
	];
	const show = (m: Metric, v: number) => (m.asPct ? pct(v) : `${fmt(v, m.nd)} ${m.unit}`);
	const tone = (m: Metric, d: number) => (m.bad === 0 || Math.abs(d) < 1e-9 ? '' : d * m.bad > 0 ? 'worse' : 'better');

	const cropBars = $derived(report ? Object.entries(report.area.cropHa).slice(0, 7) : []);
	const cropMax = $derived(Math.max(1, ...cropBars.map(([, v]) => v)));
	const soilTotal = $derived(report ? Object.values(report.area.soilHa).reduce((a, b) => a + b, 0) : 1);

	const spark = (values: number[], w = 300, h = 44) => {
		const max = Math.max(1, ...values);
		return values.map((v, i) => `${(i * w) / Math.max(1, values.length - 1)},${h - (v / max) * (h - 6) - 3}`).join(' ');
	};

	function fly(lon: number, lat: number, height = 220_000) {
		globe.viewer.camera.flyTo({ destination: globe.C.Cartesian3.fromDegrees(lon, lat, height), duration: 2.5 });
	}
	const srcTitle = (keys: string[]) =>
		report ? keys.map((k) => report.sources[k]?.path ?? k).join('\n') : keys.join(', ');
</script>

<div class="lens">
	<header>
		<div>
			<span class="eyebrow">CLIMATE LENS</span>
			<h2>Area report</h2>
		</div>
		<button class="close" aria-label="Close panel" onclick={() => panelOpen.set(false)}>×</button>
	</header>

	<div class="layers">
		<label><input type="checkbox" bind:checked={showCatchments} onchange={() => layer?.setCatchmentsVisible(showCatchments)} /> Catchments</label>
		<label><input type="checkbox" bind:checked={showParcels} onchange={() => layer?.setParcelsVisible(showParcels)} /> Contract parcels</label>
		<span class="legend">
			{#each Object.entries(SOIL_COLOR) as [soil, c] (soil)}<i style:background={c} title={soil}></i>{/each}
		</span>
	</div>

	{#if !$selectedShape}
		<section class="empty">
			<p>Draw an area over Apetit's contract farms to get a report: what grows there, peat and water, the climate ahead under three scenarios, and the actions the data supports.</p>
			<div class="buttons">
				<button onclick={() => fly(22.3, 61.05)}>Säkylä, Finland</button>
				<button onclick={() => fly(13.1, 56.0)}>Bjuv, Skåne</button>
			</div>
		</section>
	{:else if !analysis || analysis.status === 'pending'}
		<section class="empty"><p>Computing the report…</p></section>
	{:else if analysis.status === 'error'}
		<section class="empty"><p class="error">{analysis.message}</p></section>
	{:else if !lens || !lens.available}
		<section class="empty"><p class="error">{lens && !lens.available ? lens.reason : 'No Climate Lens data in the reply.'}</p></section>
	{:else if report && !hasParcels}
		<section class="empty">
			<p>No contract parcels in this area. The Apetit data covers south-west Finland around Säkylä and Skåne around Bjuv.</p>
			<div class="buttons">
				<button onclick={() => fly(22.3, 61.05)}>Go to Säkylä</button>
				<button onclick={() => fly(13.1, 56.0)}>Go to Bjuv</button>
			</div>
		</section>
	{:else if report}
		<p class="notice">{report.notice}</p>

		<!-- 1. Area at a glance -->
		<section>
			<h3><span>1</span> Area at a glance</h3>
			<div class="stats">
				<div><b>{fmt(report.area.farms)}</b>contract farms</div>
				<div><b>{fmt(report.area.parcels)}</b>field parcels</div>
				<div title={srcTitle(report.area.hectares.src)}><b>{fmt(report.area.hectares.value)}</b>ha of fields</div>
				<div title={srcTitle(report.area.contractHectares.src)}><b>{fmt(report.area.contractHectares.value)}</b>ha Apetit crops {report.package.reportYear}</div>
			</div>
			<p class="sub">
				{Object.entries(report.area.farmsBySegment).map(([s, n]) => `${n} ${SEGMENT[s] ?? s}`).join(' · ')} growers
			</p>
			<div class="bars">
				{#each cropBars as [crop, ha] (crop)}
					<div class="bar"><span>{CROP[crop] ?? crop}</span><i style:width="{(ha / cropMax) * 100}%"></i><em>{fmt(ha)} ha</em></div>
				{/each}
			</div>
			<div class="soil" title="Soil map (~88 % accurate)">
				{#each Object.entries(report.area.soilHa) as [soil, ha] (soil)}
					<i style:width="{(ha / soilTotal) * 100}%" style:background={SOIL_COLOR[soil]} title="{soil}: {fmt(ha)} ha"></i>
				{/each}
			</div>
			<p class="sub">Soil map: {Object.entries(report.area.soilHa).map(([s, ha]) => `${s.replace('_', ' ')} ${pct(ha / soilTotal)}`).join(' · ')}</p>
		</section>

		<!-- Now: live TERRA physics -->
		<section class="now">
			<h3><span>◉</span> Conditions now <small>TERRA live physics</small></h3>
			{#if now === 'loading'}
				<p class="sub">Reading the TERRA feed…</p>
			{:else if now}
				<div class="stats four">
					<div><b>{now.tempC === null ? '—' : `${fmt(now.tempC, 1)}°`}</b>air temp</div>
					<div><b>{now.rainMmH === null ? '—' : fmt(now.rainMmH, 2)}</b>rain mm/h</div>
					<div><b>{now.soilFraction === null ? '—' : pct(now.soilFraction)}</b>soil water</div>
					<div><b>{now.snowWaterMm === null ? '—' : fmt(now.snowWaterMm, 0)}</b>snow mm</div>
				</div>
				<p class="sub">{now.historical ? 'Historical replay' : 'Forecast-driven'} · {now.sourceMode} · model time {now.simTime.slice(0, 16).replace('T', ' ')} UTC. Weather tells you this week; the climate section below tells you the decades.</p>
			{:else}
				<p class="sub">TERRA is not running or not ready. Start it with <code>python3 terra/server.py</code> to see live soil water and weather here.</p>
			{/if}
		</section>

		<!-- 3. Climate risk -->
		{#if report.climate}
			{@const c = report.climate}
			{@const f = c.future[scenario][decade]}
			<section>
				<h3><span>2</span> Climate ahead</h3>
				<div class="chips">
					{#each SCENARIOS as s (s)}<button class:on={scenario === s} onclick={() => (scenario = s)} title={SCENARIO_LABEL[s]}>{SCENARIO_LABEL[s].split(' · ')[0]}</button>{/each}
				</div>
				<div class="chips">
					{#each DECADES as d (d)}<button class:on={decade === d} onclick={() => (decade = d)}>{d}</button>{/each}
				</div>
				<p class="sub">{SCENARIO_LABEL[scenario]} · {decade} vs 1991–2020, area-weighted over {c.cells.length} climate cell{c.cells.length === 1 ? '' : 's'}.</p>
				<table title={srcTitle(c.src)}>
					<thead><tr><th></th><th>1991–2020</th><th>{decade}</th><th>change</th></tr></thead>
					<tbody>
						{#each METRICS as m (m.key)}
							{@const b = c.baseline[m.key] as number}
							{@const v = f[m.key] as number}
							<tr>
								<td>{m.label}</td>
								<td>{show(m, b)}</td>
								<td>{show(m, v)}</td>
								<td class={tone(m, v - b)}>{m.asPct ? `${signed((v - b) * 100, 0)} pp` : signed(v - b, m.nd)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				<div class="spark">
					<svg viewBox="0 0 300 44" preserveAspectRatio="none" role="img" aria-label="Hot days per season 2012–2026">
						<polyline points={spark(c.history.hotDaysJJ)} />
					</svg>
					<p class="sub">Hot days per season, {c.history.years[0]}–{c.history.years.at(-1)} (simulated history). Peaks: {c.history.years.filter((_, i) => c.history.hotDaysJJ[i] >= 8).join(', ') || 'none'}.</p>
				</div>
				<p class="sub">Heat at flowering is the main driver of bad pea years in the data. Yield and € impact will come from the yield model.</p>
			</section>
		{/if}

		<!-- 4. Nature -->
		<section>
			<h3><span>3</span> Peat and water</h3>
			<div class="stats">
				<div title={srcTitle(report.peat.organicHa.src)}><b class="peat">{fmt(report.peat.organicHa.value)}</b>ha on organic soil</div>
				<div title={srcTitle(report.peat.contractCo2e.src)}><b class="peat">{fmt(report.peat.contractCo2e.value)}</b>t CO₂e/yr from peat under Apetit crops</div>
			</div>
			<p class="sub">All crops on organic soil here: {fmt(report.peat.allCropsCo2e.value)} t CO₂e/yr. Method: {String((report.constants.organicCo2TPerHa as Record<string, number>).annual)} t CO₂/ha/yr + N₂O (METHODOLOGY §5). The current calculator assumes mineral soil.</p>
			{#if report.peat.misreportCandidates.length}
				<div class="flag">
					<strong>{report.peat.misreportCandidates.length} farm{report.peat.misreportCandidates.length === 1 ? '' : 's'} to verify</strong>
					<p>≥ 30 % of contract area on organic soil per soil map, but the {report.package.reportYear} survey says mineral soil:</p>
					<p class="mono">{report.peat.misreportCandidates.map((m) => `${m.farm} (${pct(m.organicShare)})`).join(', ')}</p>
				</div>
			{/if}
			<ul class="catch">
				{#each report.catchments as k (k.id)}
					<li>
						<i style:background={STATUS_COLOR[k.status]}></i>
						<span><b>{k.id}</b> {k.water} · {k.status}{k.pSensitivity >= 1.3 ? ' · sensitive' : ''}</span>
						<em>{fmt(k.contractHaInArea)} ha here{k.load ? ` · P ${fmt(k.load.pKg)} kg/yr` : ''}</em>
					</li>
				{/each}
			</ul>
		</section>

		<!-- 5. Actions -->
		<section>
			<h3><span>4</span> Actions the data supports</h3>
			{#each report.actions as a (a.id)}
				<article class="action">
					<div class="act-head">
						<span class="id">{a.id}</span>
						<strong>{a.name}</strong>
						{#if a.flag}<span class="tag">FLAG</span>{/if}
					</div>
					<p>{a.evidence}</p>
					<p class="meta">
						{#if a.potential}<b>Up to {fmt(a.potential.value)} t CO₂e/yr here</b> · {/if}
						catalogue: {fmt(a.catalogue.abatement2030)} t group-wide by 2030{a.catalogue.eurPerT !== null ? ` · ${fmt(a.catalogue.eurPerT)} €/t` : ''} · from {a.catalogue.start}{a.catalogue.confidence ? ` · ${a.catalogue.confidence} confidence` : ''}
					</p>
					{#if a.catalogue.coBenefits}<p class="meta">Co-benefits: {a.catalogue.coBenefits}</p>{/if}
					<p class="srcs" title={srcTitle(a.src)}>Sources: {a.src.join(', ')}</p>
				</article>
			{/each}
		</section>

		<!-- 6. Evidence -->
		<section>
			<h3><span>5</span> Evidence</h3>
			<p class="sub">{report.package.name} v{report.package.version} · built {report.package.builtAt.slice(0, 16).replace('T', ' ')} UTC</p>
			<ul class="sources">
				{#each Object.entries(report.sources) as [key, s] (key)}
					<li><b>{key}</b> {s.label}<br /><code>{s.path}{s.sha256 ? ` · ${s.sha256.slice(0, 10)}…` : ''}</code></li>
				{/each}
			</ul>
		</section>

		<section class="review">
			<h3><span>6</span> Expert review</h3>
			<ReviewPanel {report} shape={$selectedShape!} />
			<p class="sub">Screen the {fmt(report.area.parcels)} parcels in this area against SBTN steps 1–2 and export the review as a PDF.</p>
			<div class="buttons">
				<button onclick={() => (sbtnBlocked = !openSbtnReview($selectedShape!))}>Open SBTN screening review ↗</button>
			</div>
			{#if sbtnBlocked}<p class="error">The browser blocked the new tab. Allow pop-ups for this site and try again.</p>{/if}
		</section>
	{/if}
</div>

<style>
	.lens {
		box-sizing: border-box;
		overflow-x: hidden;
		padding: 16px 18px 28px;
		color: var(--text);
		font-size: 12px;
		line-height: 1.5;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}
	.eyebrow {
		font-size: 9px;
		letter-spacing: 0.14em;
		color: #cfeb9b;
	}
	h2 {
		margin: 2px 0 10px;
		font-size: 18px;
		font-weight: 600;
	}
	h3 {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0 0 10px;
		font-size: 13px;
		font-weight: 600;
	}
	h3 span {
		display: inline-grid;
		place-items: center;
		width: 18px;
		height: 18px;
		border-radius: 50%;
		background: #1d3a33;
		color: #cfeb9b;
		font-size: 10px;
	}
	h3 small {
		margin-left: auto;
		font-weight: 400;
		font-size: 10px;
		color: var(--text-faint);
	}
	.close {
		background: none;
		border: 0;
		color: var(--text-dim);
		font-size: 20px;
		cursor: pointer;
	}
	section {
		padding: 14px 0;
		border-top: 1px solid var(--panel-border);
	}
	.empty p {
		color: var(--text-dim);
	}
	.notice {
		margin: 0 0 6px;
		padding: 6px 8px;
		border-radius: 6px;
		background: #2a2414;
		color: #e9cf8c;
		font-size: 10px;
	}
	.layers {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 10px;
		font-size: 11px;
		color: var(--text-dim);
	}
	.layers label {
		display: flex;
		align-items: center;
		gap: 4px;
	}
	.legend {
		margin-left: auto;
		display: flex;
		gap: 3px;
	}
	.legend i {
		width: 9px;
		height: 9px;
		border-radius: 50%;
	}
	.stats {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	.stats.four {
		grid-template-columns: repeat(4, 1fr);
	}
	.stats div {
		padding: 8px;
		border-radius: 8px;
		background: rgba(255, 255, 255, 0.04);
		color: var(--text-dim);
		font-size: 10px;
	}
	.stats b {
		display: block;
		color: var(--text);
		font-size: 17px;
		font-weight: 600;
	}
	.stats b.peat {
		color: #ff9d52;
	}
	.sub {
		margin: 8px 0 0;
		color: var(--text-faint);
		font-size: 10px;
	}
	.bars {
		margin-top: 10px;
		display: grid;
		gap: 4px;
	}
	.bar {
		display: grid;
		grid-template-columns: 78px 1fr 62px;
		align-items: center;
		gap: 8px;
		font-size: 11px;
		color: var(--text-dim);
	}
	.bar i {
		height: 7px;
		border-radius: 4px;
		background: #8fbf6a;
	}
	.bar em {
		font-style: normal;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.soil {
		display: flex;
		height: 8px;
		margin-top: 12px;
		border-radius: 4px;
		overflow: hidden;
	}
	.chips {
		display: flex;
		gap: 6px;
		margin-bottom: 6px;
	}
	.chips button,
	.buttons button {
		flex: 1;
		padding: 6px;
		border: 1px solid #385158;
		border-radius: 6px;
		background: #18313b;
		color: var(--text-dim);
		font-size: 11px;
		cursor: pointer;
	}
	.chips button.on,
	.buttons button {
		background: #cfeb9b;
		border-color: #cfeb9b;
		color: #14251a;
	}
	.buttons {
		display: flex;
		gap: 8px;
	}
	table {
		width: 100%;
		margin-top: 10px;
		border-collapse: collapse;
		font-variant-numeric: tabular-nums;
	}
	th {
		font-weight: 400;
		font-size: 10px;
		color: var(--text-faint);
		text-align: right;
	}
	td {
		padding: 5px 0;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
		text-align: right;
		white-space: nowrap;
	}
	td:first-child {
		text-align: left;
		white-space: normal;
		color: var(--text-dim);
		padding-right: 8px;
	}
	td.worse {
		color: #ff9d72;
	}
	td.better {
		color: #9fd6ff;
	}
	.spark {
		margin-top: 12px;
	}
	.spark svg {
		width: 100%;
		height: 44px;
	}
	.spark polyline {
		fill: none;
		stroke: #ff9d72;
		stroke-width: 1.5;
		vector-effect: non-scaling-stroke;
	}
	.flag {
		margin-top: 10px;
		padding: 8px 10px;
		border-left: 3px solid #ff7a1a;
		background: rgba(255, 122, 26, 0.08);
		border-radius: 4px;
	}
	.flag p {
		margin: 4px 0 0;
		color: var(--text-dim);
		font-size: 11px;
	}
	.mono,
	code {
		font-family: ui-monospace, monospace;
		font-size: 10px;
	}
	.catch {
		list-style: none;
		margin: 12px 0 0;
		padding: 0;
		display: grid;
		gap: 5px;
	}
	.catch li {
		display: grid;
		grid-template-columns: 10px 1fr auto;
		align-items: center;
		gap: 8px;
		font-size: 11px;
		color: var(--text-dim);
	}
	.catch i {
		width: 10px;
		height: 10px;
		border-radius: 2px;
	}
	.catch em {
		font-style: normal;
		color: var(--text-faint);
		font-size: 10px;
	}
	.action {
		margin-bottom: 10px;
		padding: 10px;
		border-radius: 8px;
		background: rgba(255, 255, 255, 0.035);
	}
	.act-head {
		display: flex;
		align-items: baseline;
		gap: 6px;
	}
	.act-head .id {
		font-family: ui-monospace, monospace;
		font-size: 10px;
		color: #cfeb9b;
	}
	.tag {
		margin-left: auto;
		padding: 0 5px;
		border-radius: 3px;
		background: #2c3d1f;
		color: #cfeb9b;
		font-size: 9px;
	}
	.action p {
		margin: 6px 0 0;
		color: var(--text-dim);
		font-size: 11px;
	}
	.action .meta {
		color: var(--text-faint);
		font-size: 10px;
	}
	.action .meta b {
		color: #ff9d52;
		font-weight: 600;
	}
	.srcs {
		font-size: 9px !important;
		color: var(--text-faint) !important;
	}
	.sources {
		list-style: none;
		margin: 8px 0 0;
		padding: 0;
		display: grid;
		gap: 6px;
		font-size: 10px;
		color: var(--text-dim);
	}
	.sources code {
		color: var(--text-faint);
	}
	.error {
		color: #edbb88 !important;
	}
</style>
