<script lang="ts">
	import DevReview from './DevReview.svelte';
	import { big, fmt, total, type DevData, type Item } from './types.ts';

	let data = $state<DevData | null>(null);
	let error = $state('');
	let busy = $state(false);
	let reviewer = $state(load() ?? '');
	let open = $state(false);
	let autoOpened = false;

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
			if (!autoOpened) {
				autoOpened = true;
				open = true; // first visit to the tab: go straight to the review screen
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}
	$effect(() => {
		refresh();
	});

	/** Save a person's choice. Returns true when it was stored. */
	async function choose(it: Item, choice: string): Promise<boolean> {
		if (!data) return false;
		if (!reviewer.trim()) {
			error = 'Type your name at the bottom of the card first, so the decision is signed.';
			return false;
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
			return true;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			return false;
		} finally {
			busy = false;
		}
	}

	const queue25 = $derived(data ? data.items.filter((i) => i.status === 'check' && i.year === 2025) : []);
	const decided25 = $derived(data ? queue25.filter((i) => data!.decisions[i.itemKey]).length : 0);
</script>

<div class="dev">
	<p class="eyebrow">DATA CHECK</p>
	<h2>Is every number believable?</h2>
	{#if error}<p class="error">{error}</p>{/if}
	{#if !data}
		{#if !error}<p class="sub">Loading…</p>{/if}
	{:else}
		<div class="hero">
			<div class="before"><span>Raw data</span><b>{big(total(data.run.totals.raw['2025']))}</b></div>
			<span class="arrow">→</span>
			<div class="after"><span>After the check</span><b>{big(total(data.run.totals.curated['2025']))}</b></div>
		</div>
		<p class="sub">2025 footprint, CO₂e. Typos like grams typed as kilograms made the raw files {fmt(total(data.run.totals.raw['2025']) / total(data.run.totals.curated['2025']))}× too big.</p>
		<ul class="facts">
			<li><b>{fmt(data.run.counts.fixed)}</b> typos fixed automatically</li>
			<li><b>{decided25} of {queue25.length}</b> decisions made for 2025</li>
		</ul>
		<button class="open" onclick={() => (open = true)}>Open the data check</button>
		<p class="sub">Every number is compared with a prediction from another record. Obvious typos are fixed; you decide the rest, biggest CO₂ first.</p>
	{/if}
</div>

{#if open && data}
	<DevReview {data} bind:reviewer {busy} {error} {choose} onclose={() => (open = false)} />
{/if}

<style>
	.dev { box-sizing: border-box; padding: 16px 18px 28px; font-size: 12px; line-height: 1.5; color: var(--text); }
	.eyebrow { margin: 0; font-size: 9px; letter-spacing: 0.14em; color: #cfeb9b; }
	h2 { margin: 2px 0 12px; font-size: 17px; font-weight: 600; }
	.sub { margin: 8px 0 0; color: var(--text-faint); font-size: 11px; }
	.error { color: #edbb88; }
	.hero { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 6px; }
	.hero > div { padding: 10px; border-radius: 10px; text-align: center; }
	.hero span { display: block; font-size: 10px; color: var(--text-dim); }
	.hero b { display: block; font-size: 21px; font-weight: 650; }
	.before { background: rgba(240, 120, 100, 0.12); } .before b { color: #ff9d86; }
	.after { background: rgba(120, 220, 150, 0.12); } .after b { color: #8fe3ab; }
	.arrow { color: var(--text-faint); font-size: 18px; }
	.facts { margin: 14px 0; padding: 0; list-style: none; display: grid; gap: 4px; color: var(--text-dim); font-size: 12px; }
	.facts b { color: var(--text); }
	.open { width: 100%; padding: 12px; border: 0; border-radius: 10px; background: #e9f5d3; color: #14251a; font-size: 14px; font-weight: 650; cursor: pointer; }
	.open:hover { background: #f4fbe7; }
</style>
