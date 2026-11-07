<script lang="ts">
	type Source = { level: string; source: string; statement: string; value: number | string | null };
	type Hyp = { mechanism: string; description: string; proposed: number; misfit: number };
	type Finding = {
		findingKey: string; record_key: string; issue_type: string; table: string; year: number; rule: string; evidence: string;
		field: string | null; observed: unknown; proposed: unknown; action: string; confidence: number; level: string;
		sources: Source[]; hypotheses: Hyp[]; impact_tco2e: number | null; status: string; priority: number;
		ai?: { model: string; task: string; review?: { explanation: string; verdict: 'likely_error' | 'unclear' | 'likely_legitimate'; legitimate_reason: string; suggested_check: string };
			answer?: { mechanism: string; reasoning: string; what_would_confirm: string }; code_test?: { mechanism: string; misfit: number; fits: boolean } | null } | null;
		locator?: { status_reason?: string; in_estimate?: boolean };
	};
	type Decision = { decision: string; reviewer: string; comment: string; at: string };
	type Data = {
		run: { runId: string; runAt: string; counts: { findings: number; byLevel: Record<string, number>; byStatus: Record<string, number>; checkedLegitimate: number; submitted2025: number };
			scores: { A1_dev: { score: number; precision: number; recall: number }; A2_dev: Record<string, { corrected: number; raw: number }>; baselines: Record<string, number>;
				A1_by_level: Record<string, { findings: number; precision: number }> };
			inventoryRange: Record<string, Record<string, { down: number; up: number }>>; ai: { available: boolean; model: string; notes: number } };
		findings: Finding[]; decisions: Record<string, Decision>; checked: { reason: string; count: number }[];
		inventory: { year: number; category: string; tco2e: number; tco2eUncorrected: number | null }[];
	};

	let data = $state<Data | null>(null);
	let error = $state('');
	let open = $state<string | null>(null);
	let reviewer = $state(load() ?? 'Minna (Apetit sustainability)');
	let comment = $state('');
	let busy = $state(false);

	const LEVELS: Record<string, string> = {
		A: 'Authoritative source', B: 'Independent second record', C: 'Physical or accounting constraint',
		D: 'History of the same item', E: 'Peer statistics', F: 'Model judgement (AI)', G: 'Human decision'
	};
	const STATUS: Record<string, string> = { confirmed: 'Confirmed', proposed: 'Proposed', needs_review: 'Needs review', unexplained: 'Unexplained' };

	function load() {
		try {
			return localStorage.getItem('lens.reviewer');
		} catch {
			return null;
		}
	}
	async function refresh() {
		try {
			const r = await fetch('/api/quality?limit=40');
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

	async function decide(f: Finding, decision: 'approve' | 'reject') {
		if (!data) return;
		busy = true;
		try {
			localStorage.setItem('lens.reviewer', reviewer);
		} catch {
			/* ignore */
		}
		try {
			const r = await fetch('/api/quality/review', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ findingKey: f.findingKey, runId: data.run.runId, decision, reviewer, comment })
			});
			const body = await r.json();
			if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
			data.decisions[f.findingKey] = body;
			comment = '';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	const fmt = (v: number, nd = 0) => v.toLocaleString('en-GB', { maximumFractionDigits: nd, minimumFractionDigits: nd });
	const val = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'number' ? fmt(v, Math.abs(v) < 10 ? 3 : 1) : String(v));
	const total = (cat: string) => data?.inventory.find((r) => r.year === 2025 && r.category === cat);
	const range25 = $derived(data?.run.inventoryRange?.['2025'] ?? {});
</script>

<div class="quality">
	<span class="eyebrow">DATA QUALITY · HOW APETIT'S DATA WAS CLEANED</span>
	<h2>Every correction, its evidence, and who approved it</h2>

	{#if error}<p class="error">{error}</p>{/if}
	{#if !data && !error}<p class="sub">Loading the latest run…</p>{/if}

	{#if data}
		{@const s = data.run.scores}
		<section>
			<h3>Checked against the organisers' answers <small>2023–2024</small></h3>
			<div class="stats">
				<div><b>{fmt(s.A1_dev.score, 1)}</b>error detection<em>baseline {s.baselines.A1_dev}</em></div>
				<div><b>{fmt(s.A2_dev['2023'].corrected, 1)}</b>inventory 2023<em>baseline {s.baselines.A2_2023}</em></div>
				<div><b>{fmt(s.A2_dev['2024'].corrected, 1)}</b>inventory 2024<em>baseline {s.baselines.A2_2024}</em></div>
			</div>
			<p class="sub">Precision {fmt(s.A1_dev.precision * 100, 1)} %, recall {fmt(s.A1_dev.recall * 100, 1)} %. Scored with the organisers' own scorer.</p>
		</section>

		<section>
			<h3>Evidence decides, not a model <small>precision by evidence level</small></h3>
			{#each Object.entries(s.A1_by_level).sort() as [lv, p] (lv)}
				<div class="lvl">
					<span class="pill l{lv}">{lv}</span>
					<span class="name">{LEVELS[lv]}</span>
					<i style:width="{p.precision * 100}%"></i>
					<em>{fmt(p.precision * 100, 0)} % of {p.findings}</em>
				</div>
			{/each}
			<p class="sub">
				Each correction cites the strongest evidence available. A–C corrections (registers, second records such as shipment weights, hard constraints) are applied automatically;
				D–E are proposals awaiting review. AI only explains, or suggests a known mechanism that code then tests.
			</p>
			<div class="chips">
				{#each Object.entries(data.run.counts.byStatus) as [st, n] (st)}<span class="chip {st}">{STATUS[st] ?? st} · {n}</span>{/each}
				<span class="chip legit">Left alone · {data.run.counts.checkedLegitimate}</span>
			</div>
		</section>

		<section>
			<h3>2025 inventory after cleaning <small>t CO₂e, with range</small></h3>
			<div class="stats">
				{#each [['scope1_total', 'Scope 1', 'scope1'], ['scope2_market_total', 'Scope 2 (market)', 'scope2_market'], ['scope3_total', 'Scope 3', 'scope3']] as [cat, label, key] (cat)}
					{@const t = total(cat)}
					<div>
						<b>{t ? fmt(t.tco2e) : '—'}</b>{label}
						<em>{range25[key] ? `${fmt(range25[key].down)} / +${fmt(range25[key].up)}` : 'no uncertain items'}</em>
					</div>
				{/each}
			</div>
			<p class="sub">The range shows how far each total moves if every uncertain call were wrong: anything already in the total (proposals, and soil taken from the soil map) reverted, other flags confirmed. Confirmed corrections rest on strong evidence and are not varied.</p>
		</section>

		<section>
			<h3>Review queue <small>ranked by impact × uncertainty</small></h3>
			<label class="who">Reviewer <input bind:value={reviewer} maxlength="100" /></label>
			{#each data.findings as f (f.findingKey)}
				{@const d = data.decisions[f.findingKey]}
				<article class="card" class:open={open === f.findingKey}>
					<button class="head" onclick={() => (open = open === f.findingKey ? null : f.findingKey)}>
						<span class="pill l{f.level}">{f.level}</span>
						<span class="what"><strong>{f.issue_type.replace(/_/g, ' ')}</strong><small>{f.record_key}</small></span>
						<span class="impact">{f.impact_tco2e !== null ? `${f.impact_tco2e > 0 ? '+' : ''}${fmt(f.impact_tco2e)} t` : ''}</span>
						{#if d}<span class="done {d.decision}">{d.decision === 'approve' ? '✓' : '✕'}</span>{/if}
					</button>
					{#if open === f.findingKey}
						<p class="change">{f.field ?? 'record'}: <code>{val(f.observed)}</code> → <code>{f.action === 'drop' ? 'removed' : val(f.proposed)}</code> · {STATUS[f.status]}{f.locator?.in_estimate ? ' (already in the total; reverts if rejected)' : ''} · confidence {fmt(f.confidence * 100)} %</p>
						<ul class="ev">
							{#each f.sources as e, i (i)}<li><span class="pill l{e.level}">{e.level}</span> {e.statement}<small>{e.source}</small></li>{/each}
						</ul>
						{#if f.hypotheses?.length}
							<p class="sub">Competing explanations (distance from the evidence):</p>
							<ul class="hyp">
								{#each f.hypotheses.slice(0, 3) as h (h.mechanism)}<li class:best={h === f.hypotheses[0]}>{h.description}<em>{fmt(h.misfit * 100, 0)} %</em></li>{/each}
							</ul>
						{/if}
						{#if f.ai?.review || f.ai?.answer}
							<div class="ai">
								<span class="tag">AI · {f.ai.model} · advice, not a decision</span>
								{#if f.ai.answer}<p>Suggests <b>{f.ai.answer.mechanism}</b>: {f.ai.answer.reasoning} {#if f.ai.code_test}Code test: {f.ai.code_test.fits ? 'fits' : 'does not fit'} ({fmt(f.ai.code_test.misfit * 100, 0)} % off).{/if}</p>{/if}
								{#if f.ai.review}
									<p>{f.ai.review.explanation}</p>
									<p><b>AI's call:</b> {({ likely_error: 'likely an error', unclear: 'unclear', likely_legitimate: 'likely legitimate' })[f.ai.review.verdict] ?? f.ai.review.verdict}</p>
									<p><b>Best case it is correct:</b> {f.ai.review.legitimate_reason}</p>
									<p><b>Check:</b> {f.ai.review.suggested_check}</p>
								{/if}
							</div>
						{/if}
						{#if d}
							<p class="decided">{d.decision === 'approve' ? 'Approved' : 'Rejected'} by {d.reviewer}{d.comment ? `: “${d.comment}”` : ''}</p>
						{:else}
							<textarea bind:value={comment} rows="2" placeholder="Comment (required to reject)"></textarea>
							<div class="buttons">
								<button class="approve" disabled={busy || !reviewer.trim()} onclick={() => decide(f, 'approve')}>Approve</button>
								<button class="reject" disabled={busy || !reviewer.trim() || !comment.trim()} onclick={() => decide(f, 'reject')}>Reject</button>
							</div>
						{/if}
					{/if}
				</article>
			{/each}
		</section>

		<section>
			<h3>Checked and left alone <small>look wrong, are legitimate</small></h3>
			<ul class="legit">{#each data.checked as c (c.reason)}<li><b>{c.count}</b> {c.reason}</li>{/each}</ul>
			<p class="sub">Run {data.run.runId} · {data.run.counts.findings} findings · AI notes: {data.run.ai.available ? data.run.ai.notes : 'off'} · Method: quality/METHOD.md</p>
		</section>
	{/if}
</div>

<style>
	.quality { box-sizing: border-box; overflow-x: hidden; padding: 16px 18px 28px; font-size: 12px; line-height: 1.5; color: var(--text); }
	.eyebrow { font-size: 9px; letter-spacing: 0.14em; color: #cfeb9b; }
	h2 { margin: 2px 0 12px; font-size: 16px; font-weight: 600; }
	h3 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 8px; font-size: 13px; font-weight: 600; }
	h3 small { margin-left: auto; font-size: 10px; font-weight: 400; color: var(--text-faint); }
	section { padding: 12px 0; border-top: 1px solid var(--panel-border); }
	.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
	.stats div { padding: 8px; border-radius: 8px; background: rgba(255, 255, 255, 0.04); color: var(--text-dim); font-size: 10px; }
	.stats b { display: block; color: var(--text); font-size: 18px; font-weight: 600; }
	.stats em { display: block; font-style: normal; color: var(--text-faint); }
	.sub { margin: 8px 0 0; color: var(--text-faint); font-size: 10px; }
	.error { color: #edbb88; }
	.lvl { display: grid; grid-template-columns: 22px 1fr 70px 70px; align-items: center; gap: 6px; margin: 4px 0; font-size: 11px; color: var(--text-dim); }
	.lvl i { height: 6px; border-radius: 3px; background: #8fbf6a; }
	.lvl em { font-style: normal; text-align: right; font-size: 10px; color: var(--text-faint); }
	.pill { display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 4px; font: 600 10px ui-monospace, monospace; color: #0d1a14; }
	.lA, .lB, .lC { background: #8fd18f; } .lD { background: #d8e08a; } .lE { background: #e8c27a; } .lF { background: #c6a8ea; } .lG { background: #9fc6f0; }
	.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
	.chip { padding: 2px 8px; border-radius: 999px; font-size: 10px; background: #1d2c33; color: var(--text-dim); }
	.chip.confirmed { background: #1f4a33; color: #9fe8b8; } .chip.proposed { background: #403a20; color: #e8d36b; }
	.chip.needs_review { background: #4a3626; color: #f0c6a3; } .chip.unexplained { background: #3a2a40; color: #d7a8ea; } .chip.legit { background: #22344a; color: #9fc6f0; }
	.who { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: var(--text-dim); font-size: 11px; }
	input, textarea { box-sizing: border-box; width: 100%; padding: 6px; border: 1px solid #385158; border-radius: 6px; background: #101c22; color: var(--text); font: 12px system-ui; }
	.card { margin: 6px 0; border-radius: 8px; background: rgba(255, 255, 255, 0.035); }
	.card.open { background: rgba(255, 255, 255, 0.06); padding-bottom: 8px; }
	.head { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px; border: 0; background: none; color: inherit; text-align: left; cursor: pointer; }
	.what { display: flex; flex-direction: column; flex: 1; min-width: 0; }
	.what strong { font-size: 12px; font-weight: 600; text-transform: capitalize; }
	.what small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 10px ui-monospace, monospace; color: var(--text-faint); }
	.impact { font-variant-numeric: tabular-nums; color: #ff9d72; font-size: 11px; }
	.done { font-weight: 700; } .done.approve { color: #9fe8b8; } .done.reject { color: #f0a3a3; }
	.change, .ev, .hyp, .ai, .decided, .card textarea, .card .buttons, .card .sub { margin: 6px 10px 0; }
	.change { font-size: 11px; color: var(--text-dim); }
	code { font: 11px ui-monospace, monospace; color: var(--text); }
	.ev, .hyp, .legit { list-style: none; padding: 0; display: grid; gap: 4px; font-size: 11px; color: var(--text-dim); }
	.ev small { display: block; margin-left: 24px; font-size: 9px; color: var(--text-faint); }
	.hyp li { display: flex; justify-content: space-between; gap: 8px; color: var(--text-faint); }
	.hyp li.best { color: var(--text); }
	.hyp em { font-style: normal; font-variant-numeric: tabular-nums; }
	.ai { padding: 8px; border-left: 3px solid #c6a8ea; border-radius: 4px; background: rgba(198, 168, 234, 0.08); font-size: 11px; color: var(--text-dim); }
	.ai p { margin: 4px 0 0; }
	.tag { font-size: 9px; letter-spacing: 0.06em; color: #d7a8ea; }
	.decided { font-size: 11px; color: #9fe8b8; }
	.buttons { display: flex; gap: 6px; }
	.buttons button { flex: 1; padding: 6px; border: 1px solid #385158; border-radius: 6px; background: #18313b; color: var(--text-dim); font-size: 11px; cursor: pointer; }
	.buttons button:disabled { opacity: 0.45; cursor: not-allowed; }
	.approve { background: #cfeb9b !important; border-color: #cfeb9b !important; color: #14251a !important; }
	.reject { border-color: #a85a5a !important; color: #f0b0b0 !important; }
	.legit b { color: var(--text); margin-right: 4px; }
</style>
