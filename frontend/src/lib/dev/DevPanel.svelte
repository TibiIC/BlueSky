<script lang="ts">
	type Option = { id: string; label: string; value: number | string | null; tco2e: number };
	type Item = {
		itemKey: string; series: string; record_key: string; year: number; field: string; unit: string;
		recorded: number | string; expected: number | string; expected_from: string; context: string;
		gap: number | null; status: 'fixed' | 'check'; explanation: string; options: Option[];
		default: string; inForce: string; tco2e: number; at_stake: number; ai?: { model: string; sentence: string } | null;
	};
	type Series = { label: string; expectedFrom: string; noise?: number; n?: number; flagged: number };
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
	let shown = $state(25);

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
		if (!data || !reviewer.trim()) {
			error = 'Type your name first, so the decision is signed.';
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

	const fmt = (v: number, d = 0) => (Number.isFinite(v) ? v.toLocaleString('en-GB', { maximumFractionDigits: d, minimumFractionDigits: 0 }) : '—');
	const num = (v: number | string | null) =>
		typeof v !== 'number' ? (v ?? '—') : Number.isInteger(v) && v > 1900 && v < 2100 ? String(v) : fmt(v, Math.abs(v) < 10 ? 2 : 0);
	const signed = (t: number) => (t === 0 ? '0 t' : `${t > 0 ? '+' : '−'}${fmt(Math.abs(t))} t`);
	const chosen = (it: Item) => data?.decisions[it.itemKey]?.choice ?? it.inForce ?? it.default;
	const opt = (it: Item, id: string) => it.options.find((o) => o.id === id);

	const list = $derived(
		data ? data.items.filter((i) => i.status === view && (!year || i.year === year)) : []
	);
	// What your decisions change compared with what this run applied (the next run makes it official).
	const yourDelta = $derived(
		data
			? data.items.reduce((s, it) => {
					const d = data!.decisions[it.itemKey];
					if (!d || d.choice === it.inForce) return s;
					return s + (opt(it, d.choice)?.tco2e ?? 0) - (opt(it, it.inForce)?.tco2e ?? 0);
				}, 0)
			: 0
	);
	const decidedCount = $derived(data ? data.items.filter((i) => data!.decisions[i.itemKey]).length : 0);
	const total = (t: Record<string, number> | undefined) => (t ? (t.scope1_total ?? 0) + (t.scope2_market_total ?? 0) + (t.scope3_total ?? 0) : 0);

	// Scatter: log10(expected) vs log10(recorded). Typos sit on lines parallel to the diagonal.
	const W = 300, H = 230, P = 26;
	const pts = $derived(data ? data.run.points.filter((p) => p.s === series) : []);
	const dom = $derived.by(() => {
		if (!pts.length) return { lo: 0, hi: 1 };
		const all = pts.flatMap((p) => [p.x, p.y]);
		return { lo: Math.floor(Math.min(...all)), hi: Math.ceil(Math.max(...all)) };
	});
	const sx = (v: number) => P + ((v - dom.lo) / (dom.hi - dom.lo || 1)) * (W - P - 6);
	const sy = (v: number) => H - P - ((v - dom.lo) / (dom.hi - dom.lo || 1)) * (H - P - 6);
	const seriesWithPoints = $derived(data ? Object.entries(data.run.series).filter(([k]) => data!.run.points.some((p) => p.s === k)) : []);

	function focus(k: string) {
		const it = data?.items.find((i) => i.record_key === k && i.series === series);
		if (!it) return;
		view = it.status;
		year = it.year;
		open = it.itemKey;
		shown = Math.max(shown, list.findIndex((i) => i.itemKey === it.itemKey) + 5);
	}
</script>

<div class="dev">
	<p class="eyebrow">DEV · DATA CURATION</p>
	<h2>Predict every number. Check the ones that move the footprint.</h2>
	<ol class="steps">
		<li><b>Predict</b> what each number should be, from an independent record (the shipment, the same month in other years, the system's usual top-up…).</li>
		<li><b>Compare.</b> On a log scale typos land on exact lines: ×10, ×1,000, krona as euros. If exactly one typo explains a gap, it is fixed.</li>
		<li><b>Rank by tonnes of CO₂ at stake.</b> You check the top of the list. An AI writes one plain sentence per item; it explains, it never decides.</li>
	</ol>

	{#if error}<p class="error">{error}</p>{/if}
	{#if !data}
		{#if !error}<p class="sub">Loading…</p>{/if}
	{:else}
		<section>
			<h3>Predicted vs recorded <small>log scale · each dot is one number</small></h3>
			<div class="series">
				{#each seriesWithPoints as [k, s] (k)}
					<button class:on={series === k} onclick={() => (series = k)}>{s.label} <em>{s.flagged}</em></button>
				{/each}
			</div>
			<svg viewBox="0 0 {W} {H}" role="img" aria-label="Scatter of predicted against recorded values">
				{#each [-3, -1, 0, 1, 3] as off (off)}
					<line x1={sx(dom.lo)} y1={sy(dom.lo + off)} x2={sx(dom.hi)} y2={sy(dom.hi + off)} class={off === 0 ? 'diag' : 'guide'} />
					{#if off !== 0 && dom.hi - Math.abs(off) > dom.lo}
						<text x={off > 0 ? sx(dom.hi - off) - 2 : sx(dom.hi) - 2} y={off > 0 ? sy(dom.hi) + 10 : sy(dom.hi + off) + 10} class="lbl">{off > 0 ? '×' : '÷'}{off === 1 || off === -1 ? '10' : '1,000'}</text>
					{/if}
				{/each}
				<line x1={P} y1={H - P} x2={W - 6} y2={H - P} class="axis" />
				<line x1={P} y1={6} x2={P} y2={H - P} class="axis" />
				<text x={W - 6} y={H - 8} class="lbl" text-anchor="end">predicted →</text>
				<text x={4} y={12} class="lbl">recorded ↑</text>
				{#each pts.filter((p) => p.st === 'ok') as p, i (i)}<circle cx={sx(p.x)} cy={sy(p.y)} r="1.6" class="ok" />{/each}
				{#each pts.filter((p) => p.st !== 'ok') as p (p.k)}
					<circle cx={sx(p.x)} cy={sy(p.y)} r="3.6" class={p.st} role="button" tabindex="0" onclick={() => focus(p.k)} onkeydown={(e) => e.key === 'Enter' && focus(p.k)}>
						<title>{p.k}</title>
					</circle>
				{/each}
			</svg>
			<p class="sub">
				Predicted from {data.run.series[series]?.expectedFrom}. Grey dots agree with the prediction; <span class="g">green</span> = one typo explains the gap, fixed; <span class="a">amber</span> = for you to check. Click a dot to open it.
			</p>
		</section>

		<section>
			<h3>2025 footprint <small>t CO₂e, scope 1 + 2 (market) + 3</small></h3>
			<div class="stats">
				<div><b>{fmt(total(data.run.totals.raw['2025']))}</b>raw data</div>
				<div><b>{fmt(total(data.run.totals.curated['2025']))}</b>after curation</div>
				<div><b>{fmt(data.run.awaitingTonnes['2025'] ?? 0)}</b>tonnes still awaiting a person</div>
			</div>
			{#if decidedCount}
				<p class="sub">Your decisions so far ({decidedCount}) change it by <b>{signed(yourDelta)}</b>; the next pipeline run applies them.</p>
			{/if}
			<p class="sub">
				Checked against the organisers' published answers: footprint 2023 <b>{data.run.scores.A2_dev['2023']?.curated}</b> and 2024 <b>{data.run.scores.A2_dev['2024']?.curated}</b>
				(their example: {data.run.scores.baselines.A2_2023} / {data.run.scores.baselines.A2_2024}) · errors found <b>{data.run.scores.A1_dev.score}</b> ({data.run.scores.baselines.A1_dev}).
			</p>
		</section>

		<section>
			<h3>Ranked by tonnes at stake</h3>
			<label class="who">Your name <input bind:value={reviewer} maxlength="100" placeholder="signs your decisions" /></label>
			<div class="filters">
				<button class:on={view === 'check'} onclick={() => ((view = 'check'), (shown = 25))}>For you · {data.items.filter((i) => i.status === 'check').length}</button>
				<button class:on={view === 'fixed'} onclick={() => ((view = 'fixed'), (shown = 25))}>Fixed automatically · {data.items.filter((i) => i.status === 'fixed').length}</button>
				<select bind:value={year} aria-label="Year">
					<option value={0}>All years</option>
					{#each [2025, 2024, 2023] as y (y)}<option value={y}>{y}</option>{/each}
				</select>
			</div>
			{#each list.slice(0, shown) as it (it.itemKey)}
				{@const d = data.decisions[it.itemKey]}
				<article class="card" class:open={open === it.itemKey}>
					<button class="head" onclick={() => (open = open === it.itemKey ? null : it.itemKey)}>
						<span class="dot {it.status}"></span>
						<span class="what"><strong>{data.run.series[it.series]?.label ?? it.series} · {it.context}</strong><small>{it.record_key} · {it.year}</small></span>
						<span class="stake">{fmt(it.at_stake)} t</span>
						{#if d}<span class="done" title="Decided by {d.reviewer}">✓</span>{/if}
					</button>
					{#if open === it.itemKey}
						{#if it.ai}<p class="ai"><span>AI · Claude Haiku 5.5</span>{it.ai.sentence}</p>{/if}
						<p class="change">Recorded <code>{num(it.recorded)} {it.unit}</code> · expected <code>{num(it.expected)} {it.unit}</code></p>
						<p class="why">{it.explanation}</p>
						<div class="opts">
							{#each it.options as o (o.id)}
								<button class:on={chosen(it) === o.id} disabled={busy} onclick={() => choose(it, o.id)}>
									<span>{o.label}</span><em>{signed(o.tco2e)}</em>
								</button>
							{/each}
						</div>
						<p class="sub">
							{#if d}Decided by {d.reviewer}.{:else if it.status === 'fixed'}Fixed automatically; pick another option to undo.{:else}Our best guess is applied until you decide.{/if}
						</p>
					{/if}
				</article>
			{/each}
			{#if list.length > shown}<button class="more" onclick={() => (shown += 25)}>Show more ({list.length - shown} left)</button>{/if}
			{#if !list.length}<p class="sub">Nothing here for this year.</p>{/if}
		</section>
		<p class="sub">Run {data.run.runId} · method: quality/METHOD.md</p>
	{/if}
</div>

<style>
	.dev { box-sizing: border-box; overflow-x: hidden; padding: 16px 18px 28px; font-size: 12px; line-height: 1.5; color: var(--text); }
	.eyebrow { font-size: 9px; letter-spacing: 0.14em; color: #cfeb9b; }
	h2 { margin: 2px 0 10px; font-size: 16px; font-weight: 600; line-height: 1.3; }
	h3 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 8px; font-size: 13px; font-weight: 600; }
	h3 small { margin-left: auto; font-size: 10px; font-weight: 400; color: var(--text-faint); }
	.steps { margin: 0 0 6px; padding-left: 18px; display: grid; gap: 4px; color: var(--text-dim); font-size: 11px; }
	.steps b { color: var(--text); }
	section { padding: 12px 0; border-top: 1px solid var(--panel-border); }
	.sub { margin: 8px 0 0; color: var(--text-faint); font-size: 10px; }
	.sub b { color: var(--text-dim); }
	.error { color: #edbb88; }
	.g { color: #9fe8b8; } .a { color: #f0c27a; }
	.series, .filters { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
	.series button, .filters button, .filters select, .more {
		padding: 3px 8px; border: 1px solid #385158; border-radius: 999px; background: #18313b; color: var(--text-dim); font-size: 10px; cursor: pointer;
	}
	.series button.on, .filters button.on { background: #cfeb9b; border-color: #cfeb9b; color: #14251a; }
	.series em { font-style: normal; opacity: 0.7; margin-left: 2px; }
	svg { display: block; width: 100%; height: auto; background: rgba(255, 255, 255, 0.02); border-radius: 8px; }
	.diag { stroke: #9fc6f0; stroke-width: 1; }
	.guide { stroke: #5a6f78; stroke-dasharray: 3 3; stroke-width: 0.8; }
	.axis { stroke: #385158; }
	.lbl { fill: var(--text-faint); font-size: 8px; text-anchor: end; }
	circle.ok { fill: #6f8790; opacity: 0.55; }
	circle.fixed { fill: #6fd39a; stroke: #0d1a14; stroke-width: 0.6; cursor: pointer; }
	circle.check { fill: #f0b35a; stroke: #0d1a14; stroke-width: 0.6; cursor: pointer; }
	.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
	.stats div { padding: 8px; border-radius: 8px; background: rgba(255, 255, 255, 0.04); color: var(--text-dim); font-size: 10px; }
	.stats b { display: block; color: var(--text); font-size: 17px; font-weight: 600; }
	.who { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: var(--text-dim); font-size: 11px; white-space: nowrap; }
	input { box-sizing: border-box; width: 100%; padding: 5px 6px; border: 1px solid #385158; border-radius: 6px; background: #101c22; color: var(--text); font: 12px system-ui; }
	.card { margin: 6px 0; border-radius: 8px; background: rgba(255, 255, 255, 0.035); }
	.card.open { background: rgba(255, 255, 255, 0.06); padding-bottom: 8px; }
	.head { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px; border: 0; background: none; color: inherit; text-align: left; cursor: pointer; }
	.dot { flex: none; width: 8px; height: 8px; border-radius: 50%; }
	.dot.fixed { background: #6fd39a; } .dot.check { background: #f0b35a; }
	.what { display: flex; flex-direction: column; flex: 1; min-width: 0; }
	.what strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; }
	.what small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 10px ui-monospace, monospace; color: var(--text-faint); }
	.stake { font-variant-numeric: tabular-nums; color: #ff9d72; font-size: 11px; white-space: nowrap; }
	.done { color: #9fe8b8; font-weight: 700; }
	.change, .why, .opts, .ai, .card .sub { margin: 6px 10px 0; }
	.ai { padding: 6px 8px; border-left: 3px solid #c6a8ea; border-radius: 4px; background: rgba(198, 168, 234, 0.08); font-size: 11.5px; color: var(--text); }
	.ai span { display: block; font-size: 9px; letter-spacing: 0.06em; color: #d7a8ea; }
	.change { font-size: 11px; color: var(--text-dim); }
	.why { font-size: 11px; color: var(--text-dim); }
	code { font: 11px ui-monospace, monospace; color: var(--text); }
	.opts { display: grid; gap: 4px; }
	.opts button {
		display: flex; justify-content: space-between; gap: 8px; padding: 6px 8px; border: 1px solid #385158; border-radius: 6px;
		background: #18313b; color: var(--text-dim); font-size: 11px; text-align: left; cursor: pointer;
	}
	.opts button em { font-style: normal; font-variant-numeric: tabular-nums; white-space: nowrap; }
	.opts button.on { background: #cfeb9b; border-color: #cfeb9b; color: #14251a; }
	.opts button:disabled { opacity: 0.5; cursor: wait; }
	.more { margin-top: 6px; }
</style>
