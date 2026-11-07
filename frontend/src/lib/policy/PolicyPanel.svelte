<script lang="ts">
	import { untrack } from 'svelte';
	import type { Globe } from '../globe/viewer.ts';
	import { selectedShape } from '../drawing/store.ts';
	import {
		POLICIES,
		POLICY_NOTE,
		RISKS,
		ambition,
		ambitionLabel,
		outcomes,
		pricesAt,
		riskColor,
		sspLabel,
		warmingAt,
		type Group,
		type RiskId
	} from './engine.ts';
	import { areaFacts, areaRisk, loadPolicyData, type PolicyData } from './data.ts';
	import { attachRiskLayer } from './riskLayer.ts';
	import { policyState } from './state.ts';
	import { activeTab } from '../ui/panel.ts';

	let { globe }: { globe: Globe } = $props();

	let data = $state.raw<PolicyData | null | 'loading'>('loading');
	let layer: ReturnType<typeof attachRiskLayer> | undefined;

	$effect(() => {
		const target = globe;
		let disposed = false;
		untrack(() =>
			loadPolicyData().then((d) => {
				if (disposed) return;
				data = d;
				if (d) layer = attachRiskLayer(target, d.cells, d.warming);
			})
		);
		return () => {
			disposed = true;
			layer?.destroy();
			layer = undefined;
		};
	});

	const st = $derived($policyState);
	const d = $derived(data && data !== 'loading' ? data : null);
	const s = $derived(ambition(st.active));
	const gwl = $derived(d ? warmingAt(s, st.year, d.warming) : null);
	const prices = $derived(d ? pricesAt(s, st.year, d.transition) : null);
	const area = $derived(d ? areaFacts(d.parcels, $selectedShape?.geometry ?? null) : null);
	const risk = $derived(d && gwl !== null && area ? areaRisk(st.risk, area.cellHa, gwl, d.warming) : null);
	const peaHeat = $derived(d && gwl !== null && area ? areaRisk('peaHeat', area.cellHa, gwl, d.warming) : null);
	const out = $derived(prices && area ? outcomes(st.active, st.year, prices, area) : null);
	// Bounds of the meter at this year: net zero … current policies.
	const range = $derived(d ? { lo: warmingAt(1, st.year, d.warming), mid: warmingAt(0.5, st.year, d.warming), hi: warmingAt(0, st.year, d.warming) } : null);

	$effect(() => {
		// Risk squares only while the Scenario tab is open.
		const visible = st.showMap && $activeTab === 'scenario', r = st.risk, g = gwl;
		if (!layer || g === null) return;
		layer.setVisible(visible);
		if (visible) layer.update(r, g);
	});

	function toggle(id: string) {
		if (!d) return;
		policyState.update((p) => {
			const next = new Set(p.active);
			const on = !next.has(id);
			if (on) next.add(id);
			else next.delete(id);
			const before = warmingAt(ambition(p.active), p.year, d.warming);
			const after = warmingAt(ambition(next), p.year, d.warming);
			const title = POLICIES.find((x) => x.id === id)!.title;
			return { ...p, active: next, lastChange: { title, on, deltaC: after - before } };
		});
	}
	function preset(kind: 'none' | 'adopted' | 'all') {
		const ids = kind === 'none' ? [] : kind === 'adopted' ? POLICIES.filter((p) => p.status === 'adopted').map((p) => p.id) : POLICIES.map((p) => p.id);
		policyState.update((p) => ({ ...p, active: new Set(ids), lastChange: null }));
	}
	const set = <K extends 'year' | 'risk' | 'showMap'>(k: K, v: (typeof st)[K]) => policyState.update((p) => ({ ...p, [k]: v }));

	const GROUPS: [Group, string, string][] = [
		['world', 'The world', 'Moves the warming meter'],
		['here', 'Finland & EU', 'Changes what the climate does to the land'],
		['costs', 'Costs', 'Prices that reach Apetit and its growers']
	];
	const RISK_ORDER: RiskId[] = ['composite', 'peaHeat', 'drought', 'wetHarvest', 'season', 'lateFrost'];
	const fmt = (v: number, nd = 0) => v.toLocaleString('en-GB', { maximumFractionDigits: nd, minimumFractionDigits: nd });
	const pos = (v: number) => (range ? Math.min(100, Math.max(0, ((v - 1.3) / (Math.max(range.hi, 2.7) - 1.3)) * 100)) : 0);
	const rgb = (score: number) => `rgb(${riskColor(score).join(',')})`;
	const conf = (c: number) => (c >= 0.5 ? 'high' : c >= 0.25 ? 'medium' : 'low');
	const oneIn = (p: number) => (p <= 0.001 ? 'almost never' : p >= 0.95 ? 'almost every season' : `1 in ${fmt(1 / p, p > 0.4 ? 1 : 0)} seasons`);
</script>

<div class="policy">
	<span class="eyebrow">CLIMATE LENS · SCENARIO</span>
	<h2>What the world decides, what it means for Apetit</h2>

	{#if data === 'loading'}
		<p class="sub">Loading scenario data…</p>
	{:else if !d || gwl === null || !range || !prices}
		<p class="error">Scenario data not built. Run <code>python3 lens/build_data.py</code>.</p>
	{:else}
		<!-- Meter -->
		<section class="meter">
			<div class="reading">
				<b data-testid="warming">{fmt(gwl, 2)} °C</b>
				<span>global warming in {st.year}<br /><em>{ambitionLabel(s)} · ≈ {sspLabel(s)}</em></span>
			</div>
			<div class="gauge" style:--x="{pos(gwl)}%">
				<i class="marker"></i>
				<span class="tick" style:left="{pos(range.lo)}%" title="Net zero delivered">NZ</span>
				<span class="tick" style:left="{pos(range.mid)}%" title="Pledges, SSP2-4.5">2-4.5</span>
				<span class="tick" style:left="{pos(range.hi)}%" title="Current policies">CP</span>
			</div>
			<p class="change" aria-live="polite">
				{#if st.lastChange}
					{st.lastChange.on ? 'On' : 'Off'}: {st.lastChange.title} → <b>{st.lastChange.deltaC <= 0 ? '−' : '+'}{fmt(Math.abs(st.lastChange.deltaC), 3)} °C</b>
				{:else}
					World emissions covered by active policies: {fmt(s * 100, 1)} %
				{/if}
			</p>
			<div class="presets">
				<button onclick={() => preset('none')}>Current policies</button>
				<button onclick={() => preset('adopted')}>Adopted only</button>
				<button onclick={() => preset('all')}>Everything on</button>
			</div>
		</section>

		<!-- Year and risk -->
		<section>
			<label class="year">Year <b>{st.year}</b>
				<input type="range" min="2030" max="2060" step="5" value={st.year} oninput={(e) => set('year', +e.currentTarget.value)} />
			</label>
			<div class="chips">
				{#each RISK_ORDER as r (r)}
					<button class:on={st.risk === r} onclick={() => set('risk', r)} title={RISKS[r].explain}>{RISKS[r].short}</button>
				{/each}
			</div>
			<p class="sub">
				{RISKS[st.risk].explain}
				{#if risk}<span class="conf {conf(risk.confidence)}">{conf(risk.confidence)} confidence</span>{/if}
			</p>
			<label class="maptoggle"><input type="checkbox" checked={st.showMap} onchange={(e) => set('showMap', e.currentTarget.checked)} /> Colour the map <span class="ramp"></span></label>
		</section>

		<!-- Apetit outcomes -->
		<section>
			<h3>What it means for Apetit <small>{$selectedShape ? 'drawn area' : 'all contract parcels'} · {st.year}</small></h3>
			<div class="cards">
				{#if risk}
					<div class="card" style:border-color={rgb(risk.score)}>
						<span>{RISKS[st.risk].label}</span>
						<b style:color={rgb(risk.score)}>{risk.score <= -0.05 ? 'Worse' : risk.score >= 0.05 ? 'Better' : 'Similar'}</b>
						{#if risk.value !== undefined && risk.base !== undefined}
							<em>{fmt(risk.base, st.risk === 'peaHeat' ? 2 : 1)} → {fmt(risk.value, st.risk === 'peaHeat' ? 2 : 1)} {RISKS[st.risk].unit}</em>
						{:else}<em>score {fmt(risk.score, 2)} vs 1991–2020</em>{/if}
					</div>
				{/if}
				{#if peaHeat?.value !== undefined && peaHeat.base !== undefined}
					<div class="card">
						<span>Bad pea heat seasons</span>
						<b data-testid="pea-heat">{oneIn(peaHeat.value)}</b>
						<em>1991–2020: {oneIn(peaHeat.base)}</em>
					</div>
				{/if}
				<div class="card">
					<span>EU carbon price</span>
					<b>€{fmt(prices.carbonPrice)}/t</b>
					<em>fertiliser price ×{fmt(prices.nFertiliserIndex, 2)} vs 2025</em>
				</div>
				{#if out}
					<div class="card">
						<span>Peat emissions avoided</span>
						<b>{fmt(out.peatCo2eAvoided)} t CO₂e/yr</b>
						<em>{out.peatHaOutOfCrops > 0 ? `${fmt(out.peatHaOutOfCrops, 1)} ha leave production` : 'no peat policy on'}</em>
					</div>
					<div class="card">
						<span>Grower input costs</span>
						<b>+€{fmt(out.fertiliserEurPerKgN, 2)}/kg N</b>
						<em>diesel +€{fmt(out.dieselEurPerL, 2)}/l (CBAM, ETS2)</em>
					</div>
					<div class="card">
						<span>Catch crops to add</span>
						<b>{fmt(out.catchCropHaAdded)} ha</b>
						<em>{area ? `of ${fmt(area.peaSpinachHa)} ha pea and spinach` : ''}</em>
					</div>
				{/if}
			</div>
			{#if area}<p class="sub">{fmt(area.parcels)} parcels · {fmt(area.contractHa)} ha Apetit crops (2025). Draw an area on the globe to focus.</p>{/if}
		</section>

		<!-- Policies -->
		{#each GROUPS as [g, title, hint] (g)}
			<section>
				<h3>{title} <small>{hint}</small></h3>
				{#each POLICIES.filter((p) => p.group === g) as p (p.id)}
					<label class="pol" title={p.source}>
						<input type="checkbox" checked={st.active.has(p.id)} onchange={() => toggle(p.id)} data-testid="policy-{p.id}" />
						<span>
							<strong>{p.title}</strong>
							<span class="status {p.status}">{p.status}</span>
							{#if p.meterWeight}<span class="w">{fmt(p.meterWeight * 100, p.meterWeight < 0.01 ? 1 : 0)} % of world emissions</span>{/if}
							<small>{p.summary}</small>
						</span>
					</label>
				{/each}
			</section>
		{/each}
		<p class="sub">{POLICY_NOTE}</p>
	{/if}
</div>

<style>
	.policy {
		box-sizing: border-box;
		overflow-x: hidden;
		padding: 16px 18px 28px;
		font-size: 12px;
		line-height: 1.5;
		color: var(--text);
	}
	.eyebrow {
		font-size: 9px;
		letter-spacing: 0.14em;
		color: #cfeb9b;
	}
	h2 {
		margin: 2px 0 12px;
		font-size: 16px;
		font-weight: 600;
	}
	h3 {
		display: flex;
		align-items: baseline;
		gap: 8px;
		margin: 0 0 8px;
		font-size: 13px;
		font-weight: 600;
	}
	h3 small {
		margin-left: auto;
		font-size: 10px;
		font-weight: 400;
		color: var(--text-faint);
	}
	section {
		padding: 12px 0;
		border-top: 1px solid var(--panel-border);
	}
	.meter {
		border-top: 0;
		padding-top: 0;
	}
	.reading {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.reading b {
		font-size: 34px;
		font-weight: 650;
		font-variant-numeric: tabular-nums;
	}
	.reading span {
		color: var(--text-dim);
		font-size: 11px;
	}
	.reading em {
		font-style: normal;
		color: #cfeb9b;
	}
	.gauge {
		position: relative;
		height: 10px;
		margin: 10px 0 18px;
		border-radius: 5px;
		background: linear-gradient(90deg, rgb(86, 170, 112), rgb(236, 196, 94), rgb(214, 64, 69));
	}
	.marker {
		position: absolute;
		left: var(--x);
		top: -4px;
		width: 4px;
		height: 18px;
		margin-left: -2px;
		border-radius: 2px;
		background: #fff;
		box-shadow: 0 0 6px rgba(0, 0, 0, 0.7);
		transition: left 300ms ease;
	}
	.tick {
		position: absolute;
		top: 13px;
		transform: translateX(-50%);
		font-size: 9px;
		color: var(--text-faint);
	}
	.change {
		margin: 0 0 8px;
		min-height: 18px;
		color: var(--text-dim);
		font-size: 11px;
	}
	.presets,
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.presets button,
	.chips button {
		flex: 1;
		padding: 6px;
		border: 1px solid #385158;
		border-radius: 6px;
		background: #18313b;
		color: var(--text-dim);
		font-size: 11px;
		cursor: pointer;
	}
	.chips button {
		flex: 0 0 calc(33.3% - 4px);
	}
	.chips button.on {
		background: #cfeb9b;
		border-color: #cfeb9b;
		color: #14251a;
	}
	.year {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 10px;
		color: var(--text-dim);
	}
	.year input {
		flex: 1;
	}
	.sub {
		margin: 8px 0 0;
		color: var(--text-faint);
		font-size: 10px;
	}
	.conf {
		margin-left: 4px;
		padding: 0 5px;
		border-radius: 3px;
		font-size: 9px;
	}
	.conf.high {
		background: #24402c;
		color: #9fdcae;
	}
	.conf.medium {
		background: #403a20;
		color: #e8d36b;
	}
	.conf.low {
		background: #43262a;
		color: #f0a3a3;
	}
	.maptoggle {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 8px;
		color: var(--text-dim);
		font-size: 11px;
	}
	.ramp {
		width: 70px;
		height: 6px;
		border-radius: 3px;
		background: linear-gradient(90deg, rgb(214, 64, 69), rgb(236, 196, 94), rgb(86, 170, 112));
	}
	.cards {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 8px;
		border-radius: 8px;
		border-left: 3px solid transparent;
		background: rgba(255, 255, 255, 0.04);
	}
	.card span {
		font-size: 10px;
		color: var(--text-faint);
	}
	.card b {
		font-size: 14px;
		font-weight: 600;
	}
	.card em {
		font-style: normal;
		font-size: 10px;
		color: var(--text-dim);
	}
	.pol {
		display: flex;
		gap: 8px;
		align-items: flex-start;
		padding: 6px 0;
		cursor: pointer;
	}
	.pol input {
		margin-top: 3px;
	}
	.pol strong {
		font-weight: 600;
	}
	.pol small {
		display: block;
		color: var(--text-faint);
		font-size: 10px;
	}
	.status,
	.w {
		margin-left: 6px;
		padding: 0 5px;
		border-radius: 3px;
		font-size: 9px;
		background: #1d2c33;
		color: var(--text-dim);
	}
	.status.adopted {
		background: #24402c;
		color: #9fdcae;
	}
	.status.pledged {
		background: #22344a;
		color: #9fc6f0;
	}
	.status.proposed {
		background: #403a20;
		color: #e8d36b;
	}
	.status.speculative {
		background: #3a2a40;
		color: #d7a8ea;
	}
	.error {
		color: #edbb88;
	}
	code {
		font-family: ui-monospace, monospace;
	}
</style>
