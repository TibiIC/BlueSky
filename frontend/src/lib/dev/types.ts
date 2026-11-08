export type Option = { id: string; label: string; value: number | string | null; tco2e: number };
export type Box = { q1: number; q3: number; iqr: number; normal: [number, number]; farOut: [number, number] };
export type Item = {
	itemKey: string;
	series: string;
	record_key: string;
	year: number;
	field: string;
	unit: string;
	recorded: number | string;
	expected: number | string;
	expected_from: string;
	context: string;
	gap: number | null;
	fences?: Box | null;
	status: 'fixed' | 'check';
	explanation: string;
	options: Option[];
	default: string;
	inForce: string;
	tco2e: number;
	at_stake: number;
	ai?: { model: string; sentence: string } | null;
};
export type Series = { label: string; expectedFrom: string; box?: Box; n?: number; flagged: number };
export type Point = { s: string; x: number; y: number; st: 'ok' | 'fixed' | 'check'; k: string };
export type Run = {
	runId: string;
	method: string;
	series: Record<string, Series>;
	points: Point[];
	counts: { items: number; fixed: number; check: number };
	awaitingTonnes: Record<string, number>;
	scores: { A1_dev: { score: number }; A2_dev: Record<string, { curated: number; raw: number }>; baselines: Record<string, number> };
	totals: { curated: Record<string, Record<string, number>>; raw: Record<string, Record<string, number>> };
};
export type Decision = { choice: string; reviewer: string; at: string };
export type DevData = { run: Run; items: Item[]; decisions: Record<string, Decision> };

const nf = (d: number) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: d });
export const fmt = (v: number, d = 0) => (Number.isFinite(v) ? nf(d).format(v) : '—');
export const num = (v: number | string | null) =>
	typeof v !== 'number' ? (v ?? '—') : Number.isInteger(v) && v > 1900 && v < 2100 ? String(v) : fmt(v, Math.abs(v) < 10 ? 2 : 0);
export const tonnes = (t: number) => (Math.abs(t) < 0.5 ? 'no change' : `${t > 0 ? '+' : '−'}${fmt(Math.abs(t))} t CO₂`);
export const big = (t: number) => (t >= 1e6 ? `${fmt(t / 1e6, 1)} Mt` : t >= 1e4 ? `${fmt(t / 1e3, 0)} kt` : `${fmt(t)} t`);
export function offBy(it: Item) {
	if (it.gap == null || typeof it.recorded !== 'number' || typeof it.expected !== 'number' || !it.expected || !it.recorded) return ''; // years, gas codes, soil: no ratio
	const r = it.recorded / it.expected;
	return r >= 1 ? `${fmt(r, r < 10 ? 1 : 0)}× too high` : `${fmt(1 / r, 1 / r < 10 ? 1 : 0)}× too low`;
}
export const total = (t: Record<string, number> | undefined) =>
	t ? (t.scope1_total ?? 0) + (t.scope2_market_total ?? 0) + (t.scope3_total ?? 0) : 0;
