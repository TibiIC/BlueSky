<script lang="ts">
	type Option = { id: string; label: string; value: number | string | null; tco2e: number };
	type Item = {
		itemKey: string; series: string; record_key: string; year: number; field: string; unit: string;
		recorded: number | string; expected: number | string; expected_from: string; context: string;
		gap: number | null; fences?: Box | null; status: 'fixed' | 'check'; explanation: string; options: Option[];
		default: string; inForce: string; tco2e: number; at_stake: number; ai?: { model: string; sentence: string } | null;
	};
	type Box = { q1: number; q3: number; iqr: number; normal: [number, number]; farOut: [number, number] };
	type Series = { label: string; expectedFrom: string; box?: Box; n?: number; flagged: number };
	type Point = { s: string; x: number; y: number; st: 'ok' | 'fixed' | 'check'; k: string };
	type Run = {
		runId: string; method: string; series: Record<string, Series>; points: Point[];
		counts: { items: number; fixed: number; check: number };
		awaitingTonnes: Record<string, number>;
		scores: { A1_dev: { score: number }; A2_dev: Record<string, { curated: number; raw: number }>; baselines: Record<string, number> };
		totals: { curated: Record<string, Record<string, number>>; raw: Record<string, Record<string, number>> };
	};
	type Decision = { choice: string; reviewer: string; at: string };

	let data = $state<{ run: Run; items: Item[]; decisions: Record<string, Decision> } | null>(null);
	let error = $state('');
	let busy = $state(false);
	let reviewer = $state(load() ?? '');
	let view = $state<'check' | 'fixed'>('check');
	let year = $state<number | 0>(2025);
	let series = $state('purchases');
	let open = $state<string | null>(null);
	let shown = $state(20);

	function load() {
		try {
			return localStorage.getItem('lens.reviewer');
		} catch {
			return null;
		}
	}
	async function refresh() {
		try {
			const r = await fetch('/api/dev');
			const body = await r.json();
			if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
			data = body;
			error = '';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}
	$effect(() => {
		refresh();
	});

	async function choose(it: Item, choice: string) {
		if (!data) return;
		if (!reviewer.trim()) {
			error = 'Type your name above the list first, so the decision is signed.';
			return;
		}
		busy = true;
		try {
			localStorage.setItem('lens.reviewer', reviewer);
		} catch {
			/* ignore */
		}
		try {
			const r = await fetch('/api/dev/decision', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ itemKey: it.itemKey, runId: data.run.runId, choice, reviewer })
			});
			const body = await r.json();
			if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
			data.decisions[it.itemKey] = body;
			error = '';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	// ---------- formatting
	const fmt = (v: number, d = 0) => (Number.isFinite(v) ? v.toLocaleString('en-GB', { maximumFractionDigits: d }) : '—');
	const num = (v: number | string | null) =>
		typeof v !== 'number' ? (v ?? '—') : Number.isInteger(v) && v > 1900 && v < 2100 ? String(v) : fmt(v, Math.abs(v) < 10 ? 2 : 0);
	const signed = (t: number) => (Math.abs(t) < 0.5 ? '0 t' : `${t > 0 ? '+' : '−'}${fmt(Math.abs(t))} t`);
	const big = (t: number) => (t >= 1e6 ? `${fmt(t / 1e6, 1)} Mt` : t >= 1e4 ? `${fmt(t / 1e3, 0)} kt` : `${fmt(t)} t`);
	function offBy(it: Item) {
		if (typeof it.recorded !== 'number' || typeof it.expected !== 'number' || !it.expected || !it.recorded) return '';
		const r = it.recorded / it.expected;
		return r >= 1 ? `${fmt(r, r < 10 ? 1 : 0)}× too high` : `${fmt(1 / r, 1 / r < 10 ? 1 : 0)}× too low`;
	}
	const chosen = (it: Item) => data?.decisions[it.itemKey]?.choice ?? it.inForce ?? it.default;
	const opt = (it: Item, id: string) => it.options.find((o) => o.id === id);

	// ---------- page numbers
	const total = (t: Record<string, number> | undefined) => (t ? (t.scope1_total ?? 0) + (t.scope2_market_total ?? 0) + (t.scope3_total ?? 0) : 0);
	const raw25 = $derived(data ? total(data.run.totals.raw['2025']) : 0);
	const cur25 = $derived(data ? total(data.run.totals.curated['2025']) : 0);
	const checked = $derived(data ? Object.values(data.run.series).reduce((s, v) => s + (v.box ? (v.n ?? 0) : 0), 0) : 0);
	const items = $derived(data ? data.items.filter((i) => !year || i.year === year) : []);
	const nFixed = $derived(items.filter((i) => i.status === 'fixed').length);
	const nCheck = $derived(items.filter((i) => i.status === 'check').length);
	const list = $derived(items.filter((i) => i.status === view));
	const decided = $derived(data ? data.items.filter((i) => data!.decisions[i.itemKey]).length : 0);
	const yourDelta = $derived(
		data
			? data.items.reduce((s, it) => {
					const d = data!.decisions[it.itemKey];
					if (!d || d.choice === it.inForce) return s;
					return s + (opt(it, d.choice)?.tco2e ?? 0) - (opt(it, it.inForce)?.tco2e ?? 0);
				}, 0)
			: 0
	);

	// ---------- chart: log10(predicted) vs log10(recorded)
	const W = 320, H = 240, PL = 8, PB = 18, PT = 6, PR = 6;
	const meta = $derived(data?.run.series[series]);
	const pts = $derived(data ? data.run.points.filter((p) => p.s === series) : []);
	const chartSeries = $derived(data ? Object.entries(data.run.series).filter(([k]) => data!.run.points.some((p) => p.s === k)) : []);
	const dom = $derived.by(() => {
		if (!pts.length) return { lo: 0, hi: 1 };
		const all = pts.flatMap((p) => [p.x, p.y]);
		return { lo: Math.floor(Math.min(...all) - 0.2), hi: Math.ceil(Math.max(...all) + 0.2) };
	});
	const sx = (v: number) => PL + ((v - dom.lo) / (dom.hi - dom.lo || 1)) * (W - PL - PR);
	const sy = (v: number) => H - PB - ((v - dom.lo) / (dom.hi - dom.lo || 1)) * (H - PB - PT);
	const a = 0; // no offset: the gap is simply log10(recorded / predicted)
	const MIN = Math.log10(2.5); // a flagged number is also at least 2.5x off
	// Box plot of the gaps: normal fences (1.5 IQR) and far-out fences (3 IQR, at least 2.5x)
	const normal = $derived(meta?.box?.normal ?? [-0.02, 0.02]);
	const farOut = $derived([Math.min(meta?.box?.farOut[0] ?? -MIN, -MIN), Math.max(meta?.box?.farOut[1] ?? MIN, MIN)]);
	const strip = (lo: number, hi: number) =>
		`M${sx(dom.lo)},${sy(dom.lo + lo)} L${sx(dom.hi)},${sy(dom.hi + lo)} L${sx(dom.hi)},${sy(dom.hi + hi)} L${sx(dom.lo)},${sy(dom.lo + hi)} Z`;
	const ratio = (g: number) => {
		const f = 10 ** Math.abs(g);
		if (f < 1.5) return `${g < 0 ? '−' : '+'}${fmt((f - 1) * 100, 0)} %`; // small ranges read better as percentages
		return `${g >= 0 ? '×' : '÷'}${fmt(f, f < 10 ? 1 : 0)}`;
	};
	const typoLines = [
		{ off: 3, label: '×1,000' }, { off: 1, label: '×10' }, { off: -1, label: '÷10' }, { off: -3, label: '÷1,000' }
	];
	function labelPos(off: number) {
		// where the line y = x + off leaves the plot (top edge for off > 0, right edge for off < 0)
		return off > 0 ? { x: sx(dom.hi - off - a) - 3, y: sy(dom.hi) + 10 } : { x: sx(dom.hi) - 3, y: sy(dom.hi + off + a) - 4 };
	}

	function focus(k: string) {
		const it = data?.items.find((i) => i.record_key === k && i.series === series);
		if (!it) return;
		view = it.status;
		year = it.year;
		open = it.itemKey;
		shown = Math.max(shown, list.findIndex((i) => i.itemKey === it.itemKey) + 5);
		setTimeout(() => document.getElementById(`card-${it.itemKey}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 50);
	}
</script>

<div class="dev">
	<p class="eyebrow">DEV · DATA CURATION</p>
	<h2>Apetit's raw data, cleaned up</h2>
	<p class="lead">We predict what every number should be, flag the ones far from the prediction, fix the obvious typos, and give you the rest, biggest first.</p>

	{#if error}<p class="error">{error}</p>{/if}
	{#if !data}
		{#if !error}<p class="sub">Loading…</p>{/if}
	{:else}
		<!-- 1. The result -->
		<div class="hero">
			<div class="before"><span>Raw data</span><b>{big(raw25)}</b></div>
			<div class="arrow">→</div>
			<div class="after"><span>After curation</span><b>{big(cur25)}</b></div>
		</div>
		<p class="sub center">2025 footprint, CO₂e, scope 1 + 2 + 3. The raw files overstate it <b>{fmt(raw25 / cur25)}×</b>.</p>

		<!-- 2. What happened -->
		<section>
			<h3>What happened</h3>
			<ol class="funnel">
				<li><i class="n">1</i><div><b>{fmt(checked)}</b> numbers compared with a prediction<small>each against an independent record: the shipment, the same month in other years, the usual top-up…</small></div></li>
				<li><i class="n">2</i><div><b>{fmt(data.run.counts.items)}</b> beyond the box plot's far-out fences<small>flagged for 2023–2025, plus missing months, gas codes, certificates and soil</small></div></li>
				<li class="ok"><i class="n">✓</i><div><b>{fmt(data.run.counts.fixed)}</b> fixed automatically<small>undoing exactly one typo puts it back in the normal range, e.g. kWh typed as MWh</small></div></li>
				<li class="you"><i class="n">?</i><div><b>{fmt(data.run.counts.check)}</b> need your decision<small>{fmt(data.run.awaitingTonnes['2025'] ?? 0)} t of 2025 CO₂ ride on them; our best guess is in until you decide</small></div></li>
			</ol>
		</section>

		<!-- 3. See it -->
		<section>
			<h3>See how it decides</h3>
			<label class="pick">
				<select bind:value={series} aria-label="Kind of record">
					{#each chartSeries as [k, s] (k)}<option value={k}>{s.label} ({s.flagged} flagged)</option>{/each}
				</select>
			</label>
			{#if meta?.box}
				<div class="facts">
					<span><b>{fmt(meta.n ?? 0)}</b> numbers</span>
					<span>normal: <b>{ratio(normal[0])}</b> to <b>{ratio(normal[1])}</b></span>
					<span>flagged beyond <b>{ratio(farOut[0])}</b> / <b>{ratio(farOut[1])}</b></span>
				</div>
			{/if}
			<svg viewBox="0 0 {W} {H}" role="img" aria-label="Predicted against recorded values, log scale">
				<defs><clipPath id="plot"><rect x={PL} y={PT} width={W - PL - PR} height={H - PB - PT} /></clipPath></defs>
				<g clip-path="url(#plot)">
					<path d={strip(farOut[0], farOut[1])} class="band far" />
					<path d={strip(normal[0], normal[1])} class="band" />
					{#each typoLines as t (t.off)}
						<line x1={sx(dom.lo)} y1={sy(dom.lo + a + t.off)} x2={sx(dom.hi)} y2={sy(dom.hi + a + t.off)} class="typo" />
					{/each}
					<line x1={sx(dom.lo)} y1={sy(dom.lo + a)} x2={sx(dom.hi)} y2={sy(dom.hi + a)} class="diag" />
					{#each pts.filter((p) => p.st === 'ok') as p, i (i)}<circle cx={sx(p.x)} cy={sy(p.y)} r="1.7" class="ok" />{/each}
					{#each pts.filter((p) => p.st !== 'ok') as p (p.k)}
						<circle cx={sx(p.x)} cy={sy(p.y)} r="4" class={p.st} role="button" tabindex="0" onclick={() => focus(p.k)} onkeydown={(e) => e.key === 'Enter' && focus(p.k)}>
							<title>{p.k}: click to open</title>
						</circle>
					{/each}
				</g>
				{#each typoLines as t (t.off)}
					{@const l = labelPos(t.off)}
					{#if l.x > PL + 20 && l.y > PT + 6 && l.y < H - PB}<text x={l.x} y={l.y} text-anchor="end" class="tl">{t.label}</text>{/if}
				{/each}
				<line x1={PL} y1={H - PB} x2={W - PR} y2={H - PB} class="axis" />
				<text x={W - PR} y={H - 5} text-anchor="end" class="ax">predicted →</text>
				<text x={PL + 2} y={PT + 9} class="ax">↑ recorded</text>
			</svg>
			<div class="legend">
				<span><i class="sw band"></i>normal (box plot)</span>
				<span><i class="sw band far"></i>up to the far-out fence</span>
				<span><i class="sw dot ok"></i>matches</span>
				<span><i class="sw dot fixed"></i>fixed</span>
				<span><i class="sw dot check"></i>your call</span>
				<span><i class="sw dash"></i>exact typo</span>
			</div>
			<p class="sub">
				Each dot is one number, predicted from {meta?.expectedFrom}. The bands are a box plot of recorded ÷ predicted: dark =
				normal, light = still tolerated. Beyond the light band a number is flagged. A typo multiplies a number by an exact
				factor, so it lands on a dashed line (×10, ×1,000); if undoing it puts the dot back in the dark band, it is fixed.
			</p>
		</section>

		<!-- 4. Decide -->
		<section>
			<h3>Ranked by tonnes of CO₂ at stake</h3>
			<div class="seg">
				<button class:on={view === 'check'} onclick={() => ((view = 'check'), (shown = 20))}><i class="dotc check"></i>Your decision · {nCheck}</button>
				<button class:on={view === 'fixed'} onclick={() => ((view = 'fixed'), (shown = 20))}><i class="dotc fixed"></i>Fixed · {nFixed}</button>
				<select bind:value={year} aria-label="Year">
					<option value={0}>All years</option>
					{#each [2025, 2024, 2023] as y (y)}<option value={y}>{y}</option>{/each}
				</select>
			</div>
			<label class="who">Your name <input bind:value={reviewer} maxlength="100" placeholder="signs your decisions" /></label>
			{#if decided}
				<p class="delta">You've decided {decided} so far: <b>{signed(yourDelta)}</b> on the footprint, applied on the next data refresh.</p>
			{/if}
			{#each list.slice(0, shown) as it (it.itemKey)}
				{@const d = data.decisions[it.itemKey]}
				<article class="card {it.status}" class:open={open === it.itemKey} id="card-{it.itemKey}">
					<button class="head" onclick={() => (open = open === it.itemKey ? null : it.itemKey)}>
						<i class="badge {it.status}">{it.status === 'fixed' ? '✓' : '?'}</i>
						<span class="what"><strong>{data.run.series[it.series]?.label ?? it.series}</strong><small>{it.context} · {it.year}</small></span>
						<span class="stake"><b>{fmt(it.at_stake)}</b> t</span>
						{#if d}<span class="done" title="Decided by {d.reviewer}">✔</span>{/if}
					</button>
					{#if open === it.itemKey}
						<div class="body">
							{#if it.ai}<p class="ai"><span>AI · one-sentence explanation</span>{it.ai.sentence}</p>{/if}
							<div class="compare">
								<div><small>Recorded</small><b>{num(it.recorded)}</b><em>{it.unit}</em></div>
								<div><small>Predicted</small><b>{num(it.expected)}</b><em>{it.unit}</em></div>
								{#if offBy(it)}<span class="off">{offBy(it)}</span>{/if}
							</div>
							<p class="from">Predicted from {it.expected_from}.</p>
							<p class="pickhint">{it.status === 'fixed' ? 'Applied automatically. Pick another option to undo it:' : 'Pick what is right. Our best guess is highlighted:'}</p>
							<div class="opts">
								{#each it.options as o (o.id)}
									<button class:on={chosen(it) === o.id} disabled={busy} onclick={() => choose(it, o.id)}>
										<span>{o.label}</span><em>{signed(o.tco2e)}</em>
									</button>
								{/each}
							</div>
							<p class="sub">{d ? `Decided by ${d.reviewer}.` : ''} {it.record_key}</p>
						</div>
					{/if}
				</article>
			{/each}
			{#if list.length > shown}<button class="more" onclick={() => (shown += 20)}>Show more ({list.length - shown} left)</button>{/if}
			{#if !list.length}<p class="sub">Nothing here for this year.</p>{/if}
		</section>

		<!-- 5. The statistics -->
		<section>
			<details>
				<summary>How the statistics work</summary>
				<ol class="stats-explain">
					<li><b>Ratio.</b> For each number: recorded ÷ predicted, on a log scale. 1 means it matches, 10 means ten times too high.</li>
					<li><b>Box plot.</b> For each kind of record we take the box plot of those ratios: the middle half of them (the box, quartile to quartile) and Tukey's fences. Normal fences sit 1.5 box-widths beyond the box, far-out fences 3 box-widths. Quartiles ignore extremes, so typos can't widen the box.</li>
					<li><b>Flag.</b> A number is flagged when its ratio is beyond the far-out fences and at least 2.5× off.</li>
					<li><b>Typo test.</b> A typo multiplies the true value by 10, 1,000 or 11.4 (krona). If undoing exactly one of them puts the ratio back inside the normal fences, that typo is fixed. Several or none → your decision.</li>
					<li><b>Tonnes at stake.</b> Change in the number × its emission factor, from Apetit's own calculator factors. The list is sorted by it.</li>
				</ol>
			</details>
			<p class="sub">
				Checked against the organisers' answers for 2023–2024: footprint <b>{data.run.scores.A2_dev['2023']?.curated}</b> and <b>{data.run.scores.A2_dev['2024']?.curated}</b>
				(their example {data.run.scores.baselines.A2_2023} / {data.run.scores.baselines.A2_2024}) · errors found <b>{data.run.scores.A1_dev.score}</b> ({data.run.scores.baselines.A1_dev}) · run {data.run.runId}
			</p>
		</section>
	{/if}
</div>

<style>
	.dev { box-sizing: border-box; overflow-x: hidden; padding: 16px 18px 28px; font-size: 12px; line-height: 1.5; color: var(--text); }
	.eyebrow { margin: 0; font-size: 9px; letter-spacing: 0.14em; color: #cfeb9b; }
	h2 { margin: 2px 0 4px; font-size: 17px; font-weight: 600; line-height: 1.25; }
	.lead { margin: 0 0 12px; color: var(--text-dim); font-size: 11.5px; }
	h3 { margin: 0 0 8px; font-size: 13px; font-weight: 600; }
	section { padding: 14px 0 6px; border-top: 1px solid var(--panel-border); margin-top: 10px; }
	.sub { margin: 8px 0 0; color: var(--text-faint); font-size: 10px; }
	.sub b { color: var(--text-dim); }
	.center { text-align: center; }
	.error { padding: 6px 8px; border-radius: 6px; background: rgba(237, 187, 136, 0.12); color: #edbb88; }

	/* hero */
	.hero { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 6px; }
	.hero > div:not(.arrow) { padding: 10px; border-radius: 10px; text-align: center; }
	.hero span { display: block; font-size: 10px; color: var(--text-dim); }
	.hero b { display: block; font-size: 22px; font-weight: 650; letter-spacing: -0.01em; }
	.before { background: rgba(240, 120, 100, 0.12); } .before b { color: #ff9d86; }
	.after { background: rgba(120, 220, 150, 0.12); } .after b { color: #8fe3ab; }
	.arrow { color: var(--text-faint); font-size: 18px; }

	/* funnel */
	.funnel { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
	.funnel li { display: grid; grid-template-columns: 24px 1fr; gap: 8px; align-items: start; }
	.funnel .n { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: #23363e; color: var(--text-dim); font: 600 11px system-ui; font-style: normal; }
	.funnel li.ok .n { background: #1f4a33; color: #9fe8b8; }
	.funnel li.you .n { background: #4a3a20; color: #f5c77a; }
	.funnel b { font-size: 14px; }
	.funnel small { display: block; color: var(--text-faint); font-size: 10px; line-height: 1.35; }

	/* chart */
	.pick select, .seg select { width: 100%; padding: 5px 6px; border: 1px solid #385158; border-radius: 6px; background: #101c22; color: var(--text); font-size: 11px; }
	.facts { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
	.facts span { padding: 2px 8px; border-radius: 999px; background: rgba(255, 255, 255, 0.05); color: var(--text-faint); font-size: 10px; }
	.facts b { color: var(--text); }
	svg { display: block; width: 100%; height: auto; margin-top: 6px; border-radius: 8px; background: rgba(255, 255, 255, 0.025); }
	.band { fill: rgba(159, 198, 240, 0.2); }
	.band.far { fill: rgba(159, 198, 240, 0.08); }
	.diag { stroke: #9fc6f0; stroke-width: 1.2; }
	.typo { stroke: #f0b35a; stroke-opacity: 0.55; stroke-dasharray: 4 3; stroke-width: 1; }
	.axis { stroke: #385158; }
	.ax { fill: var(--text-faint); font-size: 8.5px; }
	.tl { fill: #f0c27a; font-size: 9px; font-weight: 600; }
	circle.ok { fill: #8aa0a8; opacity: 0.5; }
	circle.fixed { fill: #6fd39a; stroke: #0d1a14; stroke-width: 0.8; cursor: pointer; }
	circle.check { fill: #f0b35a; stroke: #0d1a14; stroke-width: 0.8; cursor: pointer; }
	.legend { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 6px; color: var(--text-faint); font-size: 10px; }
	.legend span { display: inline-flex; align-items: center; gap: 4px; }
	.sw { display: inline-block; width: 10px; height: 10px; }
	.sw.band { background: rgba(159, 198, 240, 0.4); border-radius: 2px; }
	.sw.band.far { background: rgba(159, 198, 240, 0.15); }
	.sw.dot { border-radius: 50%; } .sw.ok { background: #8aa0a8; } .sw.fixed { background: #6fd39a; } .sw.check { background: #f0b35a; }
	.sw.dash { height: 0; width: 12px; border-top: 2px dashed #f0b35a; }

	/* list */
	.seg { display: grid; grid-template-columns: 1fr 1fr 82px; gap: 4px; margin-bottom: 8px; }
	.seg button { display: flex; align-items: center; justify-content: center; gap: 5px; padding: 6px; border: 1px solid #385158; border-radius: 6px; background: #18313b; color: var(--text-dim); font-size: 11px; cursor: pointer; }
	.seg button.on { background: #e9f5d3; border-color: #e9f5d3; color: #14251a; font-weight: 600; }
	.dotc { width: 8px; height: 8px; border-radius: 50%; } .dotc.fixed { background: #3fae6d; } .dotc.check { background: #e39a2f; }
	.who { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: var(--text-dim); font-size: 11px; white-space: nowrap; }
	input { box-sizing: border-box; width: 100%; padding: 5px 6px; border: 1px solid #385158; border-radius: 6px; background: #101c22; color: var(--text); font: 12px system-ui; }
	.delta { margin: 0 0 8px; padding: 6px 8px; border-radius: 6px; background: rgba(159, 198, 240, 0.1); color: var(--text-dim); font-size: 11px; }
	.card { margin: 6px 0; border-radius: 8px; background: rgba(255, 255, 255, 0.035); border-left: 3px solid transparent; }
	.card.check { border-left-color: #e39a2f; } .card.fixed { border-left-color: #3fae6d; }
	.card.open { background: rgba(255, 255, 255, 0.06); }
	.head { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px; border: 0; background: none; color: inherit; text-align: left; cursor: pointer; }
	.badge { flex: none; display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font: 700 10px system-ui; font-style: normal; }
	.badge.fixed { background: #1f4a33; color: #9fe8b8; } .badge.check { background: #4a3a20; color: #f5c77a; }
	.what { display: flex; flex-direction: column; flex: 1; min-width: 0; }
	.what strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; }
	.what small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; color: var(--text-faint); }
	.stake { white-space: nowrap; color: var(--text-faint); font-size: 10px; } .stake b { color: #ff9d72; font-size: 12px; font-variant-numeric: tabular-nums; }
	.done { color: #9fe8b8; font-weight: 700; }
	.body { padding: 0 10px 10px; }
	.ai { margin: 2px 0 8px; padding: 7px 9px; border-radius: 6px; background: rgba(198, 168, 234, 0.1); border-left: 3px solid #c6a8ea; font-size: 12px; line-height: 1.45; }
	.ai span { display: block; margin-bottom: 2px; font-size: 9px; letter-spacing: 0.06em; color: #d7a8ea; }
	.compare { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
	.compare div { padding: 6px 8px; border-radius: 6px; background: rgba(0, 0, 0, 0.18); }
	.compare small { display: block; font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em; }
	.compare b { font-size: 14px; font-variant-numeric: tabular-nums; }
	.compare em { margin-left: 4px; font-style: normal; font-size: 10px; color: var(--text-faint); }
	.off { grid-column: 1 / -1; justify-self: start; padding: 2px 8px; border-radius: 999px; background: rgba(240, 120, 100, 0.15); color: #ffab95; font-size: 10.5px; font-weight: 600; }
	.from { margin: 6px 0 0; color: var(--text-faint); font-size: 10px; }
	.pickhint { margin: 8px 0 4px; color: var(--text-dim); font-size: 10.5px; }
	.opts { display: grid; gap: 4px; }
	.opts button { display: flex; justify-content: space-between; gap: 8px; padding: 7px 9px; border: 1px solid #385158; border-radius: 6px; background: #18313b; color: var(--text-dim); font-size: 11px; text-align: left; cursor: pointer; }
	.opts button:hover { border-color: #6b8a93; }
	.opts button em { font-style: normal; font-variant-numeric: tabular-nums; white-space: nowrap; }
	.opts button.on { background: #e9f5d3; border-color: #e9f5d3; color: #14251a; font-weight: 600; }
	.opts button:disabled { opacity: 0.5; cursor: wait; }
	.more { width: 100%; margin-top: 6px; padding: 6px; border: 1px dashed #385158; border-radius: 6px; background: none; color: var(--text-dim); font-size: 11px; cursor: pointer; }

	/* statistics */
	details summary { cursor: pointer; font-size: 12px; font-weight: 600; color: var(--text); }
	.stats-explain { margin: 8px 0 0; padding-left: 18px; display: grid; gap: 6px; color: var(--text-dim); font-size: 11px; }
	.stats-explain b { color: var(--text); }
</style>
