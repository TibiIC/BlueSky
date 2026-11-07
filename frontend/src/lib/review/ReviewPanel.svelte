<script lang="ts">
	import type { LensReport } from '../lens/types.ts';
	import type { ShapeFeature } from '../drawing/types.ts';
	import { policyState } from '../policy/state.ts';
	import { reportSummary, type ReportVersion, type Review, type ReviewAction } from './model.ts';

	let { report, shape }: { report: LensReport; shape: ShapeFeature } = $props();

	type DbStatus = { configured: boolean; ok: boolean; error?: string } | null;
	let db = $state<DbStatus>(null);
	let versions = $state<ReportVersion[]>([]);
	let reviews = $state<Review[]>([]);
	let busy = $state(false);
	let error = $state('');
	let comment = $state('');
	let reviewer = $state(load('lens.reviewer') ?? 'Minna (Apetit sustainability)');

	function load(k: string) {
		try {
			return localStorage.getItem(k);
		} catch {
			return null;
		}
	}
	function remember(k: string, v: string) {
		try {
			localStorage.setItem(k, v);
		} catch {
			/* private mode: fine */
		}
	}

	const reportId = $derived(shape.properties.id);
	const latest = $derived(versions[0]);

	$effect(() => {
		fetch('/api/db')
			.then((r) => r.json())
			.then((s) => (db = s))
			.catch(() => (db = { configured: false, ok: false }));
	});
	$effect(() => {
		const id = reportId;
		if (db?.ok) refresh(id);
	});

	async function refresh(id = reportId) {
		const r = await fetch(`/api/reports?reportId=${encodeURIComponent(id)}`);
		if (!r.ok) return;
		const body = await r.json();
		if (id !== reportId) return;
		versions = body.versions;
		reviews = body.reviews;
	}

	async function save() {
		busy = true;
		error = '';
		try {
			const r = await fetch('/api/reports', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					reportId,
					name: `Area ${reportId.slice(0, 8)} · ${report.area.farms} farms`,
					author: 'Climate Lens',
					geometry: shape.geometry,
					scenario: { activePolicies: [...$policyState.active], year: $policyState.year, risk: $policyState.risk },
					summary: reportSummary(report),
					evidenceIds: ['lens.parcels', 'lens.climate', 'lens.levers', 'policy.cards']
				})
			});
			const body = await r.json();
			if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
			await refresh();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	async function decide(action: ReviewAction) {
		if (!latest) return;
		busy = true;
		error = '';
		remember('lens.reviewer', reviewer);
		try {
			const r = await fetch(`/api/reports/${encodeURIComponent(reportId)}/review`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ version: latest.version, action, reviewer, comment })
			});
			const body = await r.json();
			if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
			comment = '';
			await refresh();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	const LABEL: Record<string, string> = { draft: 'Draft', approved: 'Approved', changes_requested: 'Changes requested' };
	const ACTION: Record<ReviewAction, string> = { approve: 'approved', request_changes: 'requested changes', comment: 'commented' };
	const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
</script>

<div class="review">
	{#if !db}
		<p class="sub">Checking the database…</p>
	{:else if !db.configured}
		<p class="sub">Status: <b>Draft</b>, not saved. Add <code>MONGODB_URI</code> to <code>frontend/.env</code> to save versions and record expert approval.</p>
	{:else if !db.ok}
		<p class="error">Database unreachable: {db.error}</p>
	{:else}
		<div class="head">
			<span class="status {latest?.status ?? 'unsaved'}">{latest ? `v${latest.version} · ${LABEL[latest.status]}` : 'Not saved yet'}</span>
			<button class="save" disabled={busy} onclick={save}>{latest ? 'Save new version' : 'Save draft'}</button>
		</div>

		{#if latest}
			<label class="field">Reviewer <input bind:value={reviewer} maxlength="100" /></label>
			<textarea bind:value={comment} rows="2" maxlength="2000" placeholder="Comment (required to request changes)"></textarea>
			<div class="actions">
				<button class="approve" disabled={busy || !reviewer.trim()} onclick={() => decide('approve')}>Approve v{latest.version}</button>
				<button class="changes" disabled={busy || !reviewer.trim() || !comment.trim()} onclick={() => decide('request_changes')}>Request changes</button>
				<button class="ghost" disabled={busy || !reviewer.trim() || !comment.trim()} onclick={() => decide('comment')}>Comment</button>
			</div>

			<ol class="log">
				{#each [...reviews].reverse() as r (r.at)}
					<li><b>{r.reviewer}</b> {ACTION[r.action]} v{r.version} · <time>{when(r.at)}</time>{#if r.comment}<q>{r.comment}</q>{/if}</li>
				{/each}
				{#each versions as v (v.version)}
					<li class="ver">v{v.version} saved · <time>{when(v.createdAt)}</time> · {v.scenario.activePolicies.length} policies, {v.scenario.year}</li>
				{/each}
			</ol>
		{/if}
		<p class="sub">Saved in MongoDB Atlas. Each version is an immutable snapshot; reviews are appended, never edited.</p>
	{/if}
	{#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

<style>
	.review {
		font-size: 12px;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.status {
		padding: 2px 8px;
		border-radius: 999px;
		font-size: 11px;
		background: #2a2f36;
		color: var(--text-dim);
	}
	.status.draft {
		background: #403a20;
		color: #e8d36b;
	}
	.status.approved {
		background: #1f4a33;
		color: #9fe8b8;
	}
	.status.changes_requested {
		background: #4a2626;
		color: #f0a3a3;
	}
	button {
		padding: 6px 10px;
		border: 1px solid #385158;
		border-radius: 6px;
		background: #18313b;
		color: var(--text-dim);
		font-size: 11px;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.save,
	.approve {
		background: #cfeb9b;
		border-color: #cfeb9b;
		color: #14251a;
	}
	.changes {
		border-color: #a85a5a;
		color: #f0b0b0;
	}
	.ghost {
		background: transparent;
	}
	.field {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 10px 0 6px;
		color: var(--text-dim);
		font-size: 11px;
	}
	input,
	textarea {
		flex: 1;
		box-sizing: border-box;
		width: 100%;
		padding: 6px;
		border: 1px solid #385158;
		border-radius: 6px;
		background: #101c22;
		color: var(--text);
		font: 12px system-ui;
	}
	.actions {
		display: flex;
		gap: 6px;
		margin-top: 6px;
	}
	.log {
		margin: 10px 0 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 6px;
		color: var(--text-dim);
		font-size: 11px;
	}
	.log time {
		color: var(--text-faint);
	}
	.log q {
		display: block;
		margin-top: 2px;
		color: var(--text);
	}
	.log .ver {
		color: var(--text-faint);
	}
	.sub {
		margin: 8px 0 0;
		color: var(--text-faint);
		font-size: 10px;
	}
	.error {
		color: #edbb88;
		font-size: 11px;
	}
	code {
		font-family: ui-monospace, monospace;
	}
</style>
