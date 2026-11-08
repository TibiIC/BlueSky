<script lang="ts">
	import type { Point, Series } from './types.ts';

	/** One line from "1,000× too low" through "matches" to "1,000× too high": every number is a dot. */
	let { points, series, onpick }: { points: Point[]; series: Series | undefined; onpick?: (key: string) => void } = $props();

	const W = 720, H = 190, L = 14, R = 14, AX = 150;
	const LO = -3.6, HI = 3.6;
	const x = (g: number) => L + ((Math.max(LO, Math.min(HI, g)) - LO) / (HI - LO)) * (W - L - R);
	// deterministic jitter so the dots don't jump between renders
	function jitter(k: string) {
		let h = 0;
		for (let i = 0; i < k.length; i++) h = (h * 31 + k.charCodeAt(i)) >>> 0;
		return (h % 1000) / 1000;
	}
	const dots = $derived(
		points.map((p, i) => {
			const g = p.y - p.x;
			const spread = p.st === 'ok' ? 90 : 70;
			return { ...p, g, cx: x(g), cy: 20 + jitter(p.k ?? String(i)) * spread + (p.st === 'ok' ? 10 : 20) };
		})
	);
	const MIN = Math.log10(2.5);
	const normal = $derived(series?.box?.normal ?? [-0.02, 0.02]);
	const far = $derived([Math.min(series?.box?.farOut[0] ?? -MIN, -MIN), Math.max(series?.box?.farOut[1] ?? MIN, MIN)]);
	const ticks = [
		{ g: -3, t: '1,000× too low' }, { g: -1, t: '10× too low' }, { g: 0, t: 'matches' }, { g: 1, t: '10× too high' }, { g: 3, t: '1,000× too high' }
	];
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="How far each number is from its prediction">
	<rect x={x(far[0])} y="12" width={x(far[1]) - x(far[0])} height={AX - 12} class="far" rx="6" />
	<rect x={x(normal[0])} y="12" width={Math.max(3, x(normal[1]) - x(normal[0]))} height={AX - 12} class="normal" rx="4" />
	{#each ticks as t (t.g)}
		<line x1={x(t.g)} y1="8" x2={x(t.g)} y2={AX} class={t.g === 0 ? 'zero' : Math.abs(t.g) === 3 ? 'typo' : 'grid'} />
		<text x={x(t.g)} y={AX + 16} class="tick" text-anchor="middle">{t.t}</text>
	{/each}
	{#each dots.filter((d) => d.st === 'ok') as d, i (i)}<circle cx={d.cx} cy={d.cy} r="2.2" class="ok" />{/each}
	{#each dots.filter((d) => d.st !== 'ok') as d (d.k)}
		<circle cx={d.cx} cy={d.cy} r="5" class={d.st} role="button" tabindex="0" onclick={() => onpick?.(d.k)} onkeydown={(e) => e.key === 'Enter' && onpick?.(d.k)}>
			<title>Open this one</title>
		</circle>
	{/each}
	<text x={x(0)} y={H - 6} class="note" text-anchor="middle">← smaller than predicted · bigger than predicted →</text>
</svg>

<style>
	svg { display: block; width: 100%; height: auto; }
	.far { fill: rgba(143, 227, 171, 0.06); }
	.normal { fill: rgba(143, 227, 171, 0.18); }
	.grid { stroke: rgba(255, 255, 255, 0.08); }
	.zero { stroke: rgba(143, 227, 171, 0.55); stroke-width: 1.2; }
	.typo { stroke: #f0b35a; stroke-opacity: 0.6; stroke-dasharray: 4 3; }
	.tick { fill: var(--text-faint); font-size: 11px; }
	.note { fill: var(--text-faint); font-size: 10px; }
	circle.ok { fill: #8aa0a8; opacity: 0.45; }
	circle.fixed { fill: #6fd39a; stroke: #0d1a14; stroke-width: 1; cursor: pointer; }
	circle.check { fill: #f0b35a; stroke: #0d1a14; stroke-width: 1; cursor: pointer; }
</style>
