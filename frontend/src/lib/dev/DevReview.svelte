<script lang="ts">
	import RatioStrip from './RatioStrip.svelte';
	import { big, fmt, num, offBy, tonnes, total, type DevData, type Item } from './types.ts';

	let {
		data,
		reviewer = $bindable(''),
		busy = false,
		error = '',
		choose,
		onclose
	}: { data: DevData; reviewer: string; busy: boolean; error?: string; choose: (it: Item, id: string) => Promise<boolean>; onclose: () => void } = $props();

	let view = $state<'decide' | 'fixed' | 'how'>('decide');
	let year = $state<number | 0>(2025);
	let currentKey = $state<string | null>(null);
	let saved = $state('');
	let howSeries = $state('purchases');

	/** Render at the end of <body> so the screen sits above the globe, whatever the panel's layout. */
	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}

	const inYear = (i: Item) => !year || i.year === year;
	const decision = (i: Item) => data.decisions[i.itemKey];
	const queue = $derived(data.items.filter((i) => i.status === 'check' && inYear(i)));
	const fixedList = $derived(data.items.filter((i) => i.status === 'fixed' && inYear(i)));
	const list = $derived(view === 'fixed' ? fixedList : queue);
	const decided = $derived(queue.filter((i) => decision(i)).length);
	const leftT = $derived(queue.filter((i) => !decision(i)).reduce((s, i) => s + i.at_stake, 0));
	const current = $derived(
		list.find((i) => i.itemKey === currentKey) ?? (view === 'decide' ? (queue.find((i) => !decision(i)) ?? queue[0]) : fixedList[0])
	);
	const allDone = $derived(view === 'decide' && queue.length > 0 && decided === queue.length && !currentKey);
	const raw25 = $derived(total(data.run.totals.raw['2025']));
	const cur25 = $derived(total(data.run.totals.curated['2025']));
	const label = (i: Item) => data.run.series[i.series]?.label ?? i.series;
	const inUse = (i: Item) => decision(i)?.choice ?? i.inForce ?? i.default;

	function go(step: number) {
		if (!current || !list.length) return;
		const at = list.findIndex((i) => i.itemKey === current.itemKey);
		currentKey = list[(at + step + list.length) % list.length].itemKey;
	}
	function nextUndecided() {
		const at = queue.findIndex((i) => i.itemKey === current?.itemKey);
		const after = [...queue.slice(at + 1), ...queue.slice(0, at + 1)].find((i) => !decision(i));
		currentKey = after ? after.itemKey : null;
	}
	async function pick(id: string) {
		if (!current || busy) return;
		const it = current;
		currentKey = it.itemKey; // pin it, so "next" is counted from this item even once it is decided
		if (await choose(it, id)) {
			saved = `Saved: ${it.options.find((o) => o.id === id)?.label ?? id}`;
			setTimeout(() => (saved = ''), 1800);
			if (view === 'decide') setTimeout(nextUndecided, 450);
		}
	}
	function onkey(e: KeyboardEvent) {
		if ((e.target as HTMLElement)?.closest('input, select, textarea')) return;
		if (e.key === 'Escape') onclose();
		else if (e.key === 'ArrowRight') go(1);
		else if (e.key === 'ArrowLeft') go(-1);
		else if (view !== 'how' && current && /^[1-9]$/.test(e.key)) {
			const o = current.options[Number(e.key) - 1];
			if (o) pick(o.id);
		}
	}
	function openFromChart(k: string) {
		const it = data.items.find((i) => i.record_key === k && i.series === howSeries);
		if (!it) return;
		year = it.year;
		view = it.status === 'fixed' ? 'fixed' : 'decide';
		currentKey = it.itemKey;
	}
	const chartSeries = $derived(Object.entries(data.run.series).filter(([k]) => data.run.points.some((p) => p.s === k)));
</script>

<svelte:window onkeydown={onkey} />

<div class="overlay" use:portal>
	<div class="sheet" role="dialog" aria-modal="true" aria-label="Data check">
		<!-- header -->
		<header>
			<div class="title">
				<p class="eyebrow">DATA CHECK · APETIT</p>
				<h1>Is every number believable?</h1>
			</div>
			<div class="hero" title="2025 footprint, scope 1 + 2 + 3">
				<div class="before"><span>Raw data</span><b>{big(raw25)}</b></div>
				<span class="arrow">→</span>
				<div class="after"><span>After the check</span><b>{big(cur25)}</b></div>
				<small>2025 footprint, CO₂e</small>
			</div>
			<button class="close" onclick={onclose} aria-label="Close">Close ✕</button>
		</header>

		<!-- tabs + progress -->
		<nav>
			<div class="tabs">
				<button class:on={view === 'decide'} onclick={() => ((view = 'decide'), (currentKey = null))}>Your decisions <em>{queue.length}</em></button>
				<button class:on={view === 'fixed'} onclick={() => ((view = 'fixed'), (currentKey = null))}>Fixed automatically <em>{fixedList.length}</em></button>
				<button class:on={view === 'how'} onclick={() => (view = 'how')}>How it works</button>
			</div>
			<select bind:value={year} onchange={() => (currentKey = null)} aria-label="Year">
				{#each [2025, 2024, 2023] as y (y)}<option value={y}>{y}</option>{/each}
				<option value={0}>All years</option>
			</select>
		</nav>
		{#if view !== 'how'}
			<div class="progress">
				<div class="bar"><i style="width: {queue.length ? (100 * decided) / queue.length : 0}%"></i></div>
				<span><b>{decided} of {queue.length}</b> decided · <b>{fmt(leftT)} t</b> of CO₂ still uncertain</span>
			</div>
		{/if}

		<!-- body -->
		{#if view === 'how'}
			<div class="how">
				<ol class="steps">
					<li><i>1</i><b>Predict</b>Every number gets an expected value from another record: the truck's weight for a purchase, the same month last year for a meter, the usual refill for a freezer.</li>
					<li><i>2</i><b>Compare</b>We divide the number by its prediction. Most land on "matches". Typos land exactly on 10× or 1,000×, because that's what a slipped decimal or wrong unit does.</li>
					<li><i>3</i><b>Fix or ask</b>If undoing one typo puts it back in the normal range, we fix it. Everything else comes to you, biggest CO₂ first, with a one-sentence explanation.</li>
				</ol>
				<div class="chart">
					<div class="chips">
						{#each chartSeries as [k, s] (k)}<button class:on={howSeries === k} onclick={() => (howSeries = k)}>{s.label}</button>{/each}
					</div>
					<h3>{data.run.series[howSeries]?.label}: each dot is one number, compared with {data.run.series[howSeries]?.expectedFrom}</h3>
					<RatioStrip points={data.run.points.filter((p) => p.s === howSeries)} series={data.run.series[howSeries]} onpick={openFromChart} />
					<div class="legend">
						<span><i class="sw normal"></i>normal range</span>
						<span><i class="sw dot ok"></i>matches its prediction</span>
						<span><i class="sw dot fixed"></i>typo, fixed automatically</span>
						<span><i class="sw dot check"></i>for you to decide</span>
					</div>
				</div>
				<details>
					<summary>For statisticians</summary>
					<p>
						Per kind of record we take log₁₀(recorded ÷ predicted) and its box plot. A number is flagged beyond Tukey's far-out fences
						(3 IQR beyond the quartiles) and at least 2.5× off. A typo (×10, ×100, ×1,000, ×11.4 krona) is accepted if undoing it lands
						inside the normal fences (1.5 IQR, at least ±5 %); exactly one accepted typo means an automatic fix. Tonnes at stake = change ×
						emission factor. Checked on the organisers' 2023–2024 answers: footprint {data.run.scores.A2_dev['2023']?.curated} /
						{data.run.scores.A2_dev['2024']?.curated} (their example {data.run.scores.baselines.A2_2023} / {data.run.scores.baselines.A2_2024}),
						errors found {data.run.scores.A1_dev.score} ({data.run.scores.baselines.A1_dev}).
					</p>
				</details>
			</div>
		{:else}
			<div class="body">
				<main>
					{#if allDone}
						<div class="done">
							<h2>All {queue.length} decided{year ? ` for ${year}` : ''}.</h2>
							<p>Thank you, {reviewer || 'reviewer'}. Your choices are saved; the next data refresh applies them to the footprint.</p>
							<button onclick={() => (currentKey = queue[0]?.itemKey ?? null)}>Look through them again</button>
						</div>
					{:else if current}
						{@const it = current}
						{@const d = decision(it)}
						<article class="card {it.status}">
							<div class="meta">
								<span class="cat">{label(it)}</span>
								<span class="where">{it.context} · {it.year}</span>
								<span class="stake"><b>{fmt(it.at_stake)} t</b> CO₂ at stake</span>
							</div>
							{#if it.ai}
								<blockquote>{it.ai.sentence}<cite>Explained by AI · it never decides</cite></blockquote>
							{:else}
								<blockquote>{it.explanation}</blockquote>
							{/if}
							<div class="tiles">
								<div><small>Recorded</small><b>{num(it.recorded)}</b><em>{it.unit}</em></div>
								<div><small>Expected</small><b>{num(it.expected)}</b><em>{it.unit}</em><span>from {it.expected_from}</span></div>
								{#if offBy(it)}<div class="off"><small>Difference</small><b>{offBy(it)}</b></div>{/if}
							</div>
							<h3>{it.status === 'fixed' ? 'We fixed this automatically. Keep it?' : 'What should we use?'}</h3>
							<div class="opts">
								{#each it.options as o, n (o.id)}
									<button class:on={inUse(it) === o.id} class:suggest={o.id === it.default} disabled={busy} onclick={() => pick(o.id)}>
										<kbd>{n + 1}</kbd>
										<span class="lab">{o.label}{#if o.id === it.default}<em>{it.status === 'fixed' ? 'applied' : 'our suggestion'}</em>{/if}</span>
										<span class="t">{tonnes(o.tco2e)}</span>
									</button>
								{/each}
							</div>
							<footer>
								<button class="nav" onclick={() => go(-1)}>← Previous</button>
								<span class="who">{d ? `Decided by ${d.reviewer}` : 'Signing as'} <input bind:value={reviewer} maxlength="100" placeholder="your name" /></span>
								<button class="nav" onclick={() => go(1)}>Skip →</button>
							</footer>
						</article>
					{:else}
						<div class="done"><h2>Nothing here for this year.</h2></div>
					{/if}
					{#if saved}<div class="toast">✓ {saved}</div>{/if}
					{#if error}<div class="toast err">{error}</div>{/if}
				</main>
				<aside>
					<h4>{view === 'fixed' ? 'Fixed automatically, biggest first' : 'Up next, biggest CO₂ first'}</h4>
					<ul>
						{#each list as i (i.itemKey)}
							<li>
								<button class:cur={current?.itemKey === i.itemKey} class:dec={!!decision(i)} onclick={() => (currentKey = i.itemKey)}>
									<i class="st {i.status}">{decision(i) ? '✓' : i.status === 'fixed' ? '✓' : '?'}</i>
									<span><b>{label(i)}</b><small>{i.context}</small></span>
									<em>{fmt(i.at_stake)} t</em>
								</button>
							</li>
						{/each}
					</ul>
					<p class="keys">Keys: <kbd>1</kbd>–<kbd>3</kbd> choose · <kbd>←</kbd> <kbd>→</kbd> move · <kbd>Esc</kbd> close</p>
				</aside>
			</div>
		{/if}
	</div>
</div>

<style>
	.overlay { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; background: rgba(3, 6, 12, 0.66); backdrop-filter: blur(6px); }
	.sheet {
		display: grid; grid-template-rows: auto auto auto 1fr; width: min(1200px, calc(100vw - 32px)); height: calc(100vh - 32px);
		border: 1px solid var(--panel-border); border-radius: 16px; background: rgba(12, 17, 26, 0.97); box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
		color: var(--text); overflow: hidden; font-size: 14px;
	}
	header { display: grid; grid-template-columns: 1fr auto auto; align-items: center; gap: 20px; padding: 18px 24px 10px; }
	.eyebrow { margin: 0; font-size: 10px; letter-spacing: 0.16em; color: #cfeb9b; }
	h1 { margin: 2px 0 0; font-size: 24px; font-weight: 650; letter-spacing: -0.01em; }
	.hero { display: grid; grid-template-columns: auto auto auto; align-items: center; gap: 10px; text-align: center; }
	.hero > div { padding: 6px 14px; border-radius: 10px; }
	.hero span { display: block; font-size: 11px; color: var(--text-dim); }
	.hero b { font-size: 22px; font-weight: 650; }
	.hero small { grid-column: 1 / -1; font-size: 10px; color: var(--text-faint); }
	.before { background: rgba(240, 120, 100, 0.13); } .before b { color: #ff9d86; }
	.after { background: rgba(120, 220, 150, 0.13); } .after b { color: #8fe3ab; }
	.arrow { color: var(--text-faint); font-size: 20px; }
	.close { padding: 8px 14px; border: 1px solid #385158; border-radius: 8px; background: #18313b; color: var(--text); font-size: 13px; cursor: pointer; }

	nav { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 4px 24px 0; }
	.tabs { display: flex; gap: 6px; }
	.tabs button { padding: 8px 14px; border: 0; border-radius: 999px; background: transparent; color: var(--text-dim); font-size: 14px; cursor: pointer; }
	.tabs button.on { background: #e9f5d3; color: #14251a; font-weight: 600; }
	.tabs em { margin-left: 4px; font-style: normal; opacity: 0.7; }
	nav select { padding: 6px 8px; border: 1px solid #385158; border-radius: 8px; background: #101c22; color: var(--text); font-size: 13px; }
	.progress { display: flex; align-items: center; gap: 14px; padding: 12px 24px 6px; color: var(--text-dim); font-size: 13px; }
	.progress b { color: var(--text); }
	.bar { flex: 0 0 240px; height: 8px; border-radius: 999px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
	.bar i { display: block; height: 100%; background: linear-gradient(90deg, #6fd39a, #cfeb9b); transition: width 0.3s; }

	.body { display: grid; grid-template-columns: 1fr 340px; gap: 18px; min-height: 0; padding: 8px 24px 20px; }
	main { position: relative; min-height: 0; overflow-y: auto; }
	.card { padding: 22px 24px; border-radius: 14px; background: rgba(255, 255, 255, 0.04); border-top: 4px solid #e39a2f; }
	.card.fixed { border-top-color: #3fae6d; }
	.meta { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; }
	.cat { padding: 3px 10px; border-radius: 999px; background: rgba(255, 255, 255, 0.08); font-size: 12px; font-weight: 600; }
	.where { color: var(--text-dim); font-size: 13px; }
	.stake { margin-left: auto; color: var(--text-faint); font-size: 13px; } .stake b { color: #ff9d72; font-size: 18px; }
	blockquote { margin: 18px 0; padding: 0 0 0 16px; border-left: 4px solid #c6a8ea; font-size: 20px; line-height: 1.4; font-weight: 500; }
	cite { display: block; margin-top: 6px; font-size: 11px; font-style: normal; color: #d7a8ea; letter-spacing: 0.04em; }
	.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }
	.tiles div { padding: 10px 14px; border-radius: 10px; background: rgba(0, 0, 0, 0.22); }
	.tiles small { display: block; font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em; }
	.tiles b { font-size: 22px; font-variant-numeric: tabular-nums; }
	.tiles em { margin-left: 6px; font-style: normal; color: var(--text-faint); font-size: 13px; }
	.tiles span { display: block; font-size: 11px; color: var(--text-faint); }
	.tiles .off b { color: #ffab95; font-size: 18px; }
	h3 { margin: 22px 0 10px; font-size: 15px; font-weight: 600; }
	.opts { display: grid; gap: 8px; }
	.opts button {
		display: grid; grid-template-columns: 26px 1fr auto; align-items: center; gap: 12px; padding: 13px 16px; border: 1px solid #385158;
		border-radius: 10px; background: #15262e; color: var(--text); font-size: 15px; text-align: left; cursor: pointer;
	}
	.opts button:hover { border-color: #8fb3bd; }
	.opts button.suggest { border-color: #6b8a93; }
	.opts button.on { background: #e9f5d3; border-color: #e9f5d3; color: #14251a; font-weight: 600; }
	.opts button:disabled { opacity: 0.6; cursor: wait; }
	.lab em { margin-left: 8px; padding: 1px 8px; border-radius: 999px; background: rgba(207, 235, 155, 0.18); color: #cfeb9b; font-size: 11px; font-style: normal; font-weight: 600; }
	.opts button.on .lab em { background: rgba(20, 37, 26, 0.12); color: #14251a; }
	.t { color: var(--text-faint); font-size: 13px; font-variant-numeric: tabular-nums; }
	.opts button.on .t { color: #2f4a35; }
	kbd { display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 4px; border: 1px solid #4a6670; border-radius: 4px; font: 600 11px ui-monospace, monospace; color: var(--text-dim); }
	.opts button.on kbd { border-color: #6a8a6f; color: #14251a; }
	footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 18px; }
	.nav { padding: 8px 12px; border: 0; background: none; color: var(--text-dim); font-size: 13px; cursor: pointer; }
	.nav:hover { color: var(--text); }
	.who { display: flex; align-items: center; gap: 8px; color: var(--text-faint); font-size: 12px; }
	.who input { width: 200px; padding: 6px 8px; border: 1px solid #385158; border-radius: 6px; background: #101c22; color: var(--text); font-size: 13px; }
	.done { padding: 40px; text-align: center; color: var(--text-dim); }
	.done h2 { color: var(--text); }
	.done button { padding: 8px 14px; border: 1px solid #385158; border-radius: 8px; background: #18313b; color: var(--text); cursor: pointer; }
	.toast.err { background: #4a3626; color: #f0c6a3; }
	.toast { position: sticky; bottom: 8px; margin: 10px auto 0; width: fit-content; padding: 8px 14px; border-radius: 999px; background: #1f4a33; color: #9fe8b8; font-size: 13px; }

	aside { display: grid; grid-template-rows: auto 1fr auto; min-height: 0; }
	aside h4 { margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--text-dim); }
	aside ul { margin: 0; padding: 0; list-style: none; overflow-y: auto; }
	aside li button { display: grid; grid-template-columns: 20px 1fr auto; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; border: 0; border-radius: 8px; background: none; color: var(--text); text-align: left; cursor: pointer; }
	aside li button:hover { background: rgba(255, 255, 255, 0.04); }
	aside li button.cur { background: rgba(233, 245, 211, 0.1); }
	aside li button.dec { opacity: 0.55; }
	.st { display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font: 700 10px system-ui; font-style: normal; }
	.st.check { background: #4a3a20; color: #f5c77a; } .st.fixed { background: #1f4a33; color: #9fe8b8; }
	aside li span { min-width: 0; }
	aside li b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 600; }
	aside li small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: var(--text-faint); }
	aside li em { font-style: normal; color: #ff9d72; font-size: 12px; font-variant-numeric: tabular-nums; }
	.keys { margin: 8px 0 0; color: var(--text-faint); font-size: 11px; }
	.keys kbd { min-width: 16px; height: 16px; font-size: 10px; }

	.how { min-height: 0; overflow-y: auto; padding: 14px 24px 24px; }
	.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 0 0 18px; padding: 0; list-style: none; }
	.steps li { padding: 16px; border-radius: 12px; background: rgba(255, 255, 255, 0.04); color: var(--text-dim); font-size: 14px; line-height: 1.5; }
	.steps i { display: inline-grid; place-items: center; width: 26px; height: 26px; margin-right: 8px; border-radius: 50%; background: #e9f5d3; color: #14251a; font: 700 13px system-ui; font-style: normal; }
	.steps b { display: inline; color: var(--text); font-size: 16px; }
	.steps b::after { content: ''; display: block; margin-bottom: 6px; }
	.chart { padding: 16px; border-radius: 12px; background: rgba(255, 255, 255, 0.03); }
	.chart h3 { margin: 10px 0 4px; font-size: 14px; color: var(--text-dim); font-weight: 500; }
	.chips { display: flex; flex-wrap: wrap; gap: 6px; }
	.chips button { padding: 5px 11px; border: 1px solid #385158; border-radius: 999px; background: #15262e; color: var(--text-dim); font-size: 12px; cursor: pointer; }
	.chips button.on { background: #e9f5d3; border-color: #e9f5d3; color: #14251a; font-weight: 600; }
	.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 4px; color: var(--text-faint); font-size: 12px; }
	.legend span { display: inline-flex; align-items: center; gap: 6px; }
	.sw { display: inline-block; width: 12px; height: 12px; }
	.sw.normal { background: rgba(143, 227, 171, 0.35); border-radius: 3px; }
	.sw.dot { border-radius: 50%; } .sw.ok { background: #8aa0a8; } .sw.fixed { background: #6fd39a; } .sw.check { background: #f0b35a; }
	details { margin-top: 16px; color: var(--text-dim); font-size: 13px; }
	summary { cursor: pointer; color: var(--text); }
</style>
