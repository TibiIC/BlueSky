import type { Polygon } from 'geojson';
import { PUBLIC_STRATEGY_URL } from '$app/env/public';
import { POLICIES, ambition, ambitionLabel, pricesAt, sspLabel, warmingAt } from './engine.ts';
import type { PolicyData } from './data.ts';
import type { PolicyState } from './state.ts';

/** What the strategy page (backend /strategy) reads from the URL fragment. */
export interface StrategyHandoff {
	name: string;
	/** Selected area as polygon coordinates (outer ring first); null for the whole portfolio. */
	selection: Polygon['coordinates'][] | null;
	scenario: {
		year: number;
		warmingC: number | null;
		pathway: string;
		policies: { title: string; status: string }[];
		compliancePct: number;
		carbonPriceEurT: number | null;
	};
}

const round5 = (v: number) => Math.round(v * 1e5) / 1e5;

/**
 * Link to the Farm Missions strategy page with the Scenario settings and, if any, the selected area.
 * The data rides in the fragment (#…), which browsers never send to a server.
 */
export function strategyHref(state: PolicyState, data: PolicyData | null, area: Polygon | null): string {
	const s = ambition(state.active);
	const handoff: StrategyHandoff = {
		name: area ? `Globe selection ${new Date().toISOString().slice(0, 16).replace('T', ' ')}` : 'Whole portfolio',
		selection: area ? [area.coordinates.map((ring) => ring.map(([x, y]) => [round5(x), round5(y)]))] : null,
		scenario: {
			year: state.year,
			warmingC: data ? Math.round(warmingAt(s, state.year, data.warming) * 100) / 100 : null,
			pathway: `${ambitionLabel(s)} ≈ ${sspLabel(s)}`,
			policies: POLICIES.filter((p) => state.active.has(p.id)).map((p) => ({ title: p.title, status: p.status })),
			compliancePct: Math.round(state.compliance * 100),
			carbonPriceEurT: data ? Math.round(pricesAt(s, state.year, data.transition).carbonPrice) : null
		}
	};
	return `${PUBLIC_STRATEGY_URL}#${encodeURIComponent(JSON.stringify(handoff))}`;
}
