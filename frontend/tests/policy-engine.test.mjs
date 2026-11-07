import test from 'node:test';
import assert from 'node:assert/strict';
import { POLICIES, ambition, warmingAt, pricesAt, cellRisk, riskColor, outcomes, RISKS } from '../src/lib/policy/engine.ts';
import { areaFacts, areaRisk } from '../src/lib/policy/data.ts';

// Small synthetic fixtures with the same shape as warming.json / transition.json.
const warming = {
	baselineGwl: 0.9,
	gwl: {},
	ar6: { bestEstimate: { ssp126: [1.5, 1.7, 1.8], ssp245: [1.5, 2.0, 2.7], ssp585: [1.6, 2.4, 4.4] } },
	cells: {
		A: {
			pHeatSeason: { base: 0.1, slope: 0.25, r2: 0.6 },
			waterBalanceMJJA: { base: -200, slope: -10, r2: 0.05 },
			heavyRainDaysJAS: { base: 1.3, slope: 0.2, r2: 0.05 },
			gdd5: { base: 1400, slope: 320, r2: 0.95 },
			frostDaysMay: { base: 1, slope: -0.2, r2: 0.3 }
		},
		B: {
			pHeatSeason: { base: 0.3, slope: 0.25, r2: 0.6 },
			waterBalanceMJJA: { base: -250, slope: -10, r2: 0.05 },
			heavyRainDaysJAS: { base: 1.5, slope: 0.2, r2: 0.05 },
			gdd5: { base: 1500, slope: 320, r2: 0.95 },
			frostDaysMay: { base: 0.5, slope: -0.2, r2: 0.3 }
		}
	}
};
const series = (v) => [v, v, v, v, v, v, v];
const scen = (ssp, carbon) => ({ ssp, years: [2025, 2027, 2030, 2035, 2040, 2045, 2050], carbonPrice: series(carbon), ets2Price: series(50), nFertiliserIndex: series(1.1), dieselIndex: series(1), importPremiumPct: series(5) });
const transition = { scenarios: { current_policies: scen('ssp585', 100), ndcs: scen('ssp245', 150), below_2c: scen('ssp126', 300), net_zero_2050: scen('ssp126', 600) } };
const world = POLICIES.filter((p) => p.group === 'world').map((p) => p.id);

test('catalogue: unique ids, sources, world weights sum to 1, local cards barely weigh', () => {
	assert.equal(new Set(POLICIES.map((p) => p.id)).size, POLICIES.length);
	for (const p of POLICIES) assert.ok(p.source && p.summary && p.title, p.id);
	const w = POLICIES.filter((p) => p.group === 'world').reduce((s, p) => s + p.meterWeight, 0);
	assert.ok(Math.abs(w - 1) < 1e-9);
	for (const p of POLICIES.filter((p) => p.group !== 'world')) assert.ok((p.meterWeight ?? 0) <= 0.001, p.id);
});

test('ambition: no policies is current policies, all world cards is net zero, capped at 1', () => {
	assert.equal(ambition(new Set()), 0);
	assert.ok(Math.abs(ambition(new Set(world)) - 1) < 1e-9);
	assert.equal(ambition(new Set(POLICIES.map((p) => p.id))), 1);
});

test('warming follows the AR6 pathways and falls with ambition', () => {
	// 2050 sits between the 2021–2040 and 2041–2060 centres (2030.5, 2050.5).
	const at2050 = (a, b) => a + (b - a) * (19.5 / 20);
	assert.ok(Math.abs(warmingAt(0, 2050, warming) - at2050(1.6, 2.4)) < 1e-9, 'current policies = SSP5-8.5');
	assert.ok(Math.abs(warmingAt(0.5, 2050, warming) - at2050(1.5, 2.0)) < 1e-9, 'pledges = SSP2-4.5');
	assert.ok(Math.abs(warmingAt(1, 2050, warming) - at2050(1.5, 1.7)) < 1e-9, 'net zero = SSP1-2.6');
	for (let y = 2030; y <= 2060; y += 5)
		for (let s = 0; s < 1; s += 0.1) assert.ok(warmingAt(s + 0.1, y, warming) <= warmingAt(s, y, warming) + 1e-12, `${y} ${s}`);
});

test("Finland alone moves warming by less than a hundredth of a degree; China moves it a lot", () => {
	const d = (ids) => warmingAt(0, 2050, warming) - warmingAt(ambition(new Set(ids)), 2050, warming);
	assert.ok(d(['fi_climate_act']) > 0 && d(['fi_climate_act']) < 0.01);
	assert.ok(d(['world_china']) > 0.2);
});

test('prices interpolate the NGFS scenarios; ETS2 starts in 2028', () => {
	assert.equal(pricesAt(0, 2040, transition).carbonPrice, 100);
	assert.equal(pricesAt(0.5, 2040, transition).carbonPrice, 150);
	assert.equal(pricesAt(1, 2040, transition).carbonPrice, 600);
	assert.equal(pricesAt(0.25, 2040, transition).carbonPrice, 125);
	assert.equal(pricesAt(1, 2027, transition).ets2Price, 0);
	assert.equal(pricesAt(1, 2030, transition).ets2Price, 50);
});

test('cell risk: change scales with warming, sign means worse/better, scores clamp to [-1, 1]', () => {
	const c = warming.cells.A;
	const heat = cellRisk('peaHeat', c, 1.7, warming);
	assert.ok(Math.abs(heat.delta - 0.25 * 0.8) < 1e-9);
	assert.ok(heat.score < 0, 'more heat seasons is worse');
	assert.ok(cellRisk('season', c, 1.7, warming).score > 0, 'longer season is an opportunity');
	assert.ok(cellRisk('lateFrost', c, 1.7, warming).score > 0, 'fewer late frosts is better');
	assert.ok(cellRisk('drought', c, 1.7, warming).score < 0, 'lower water balance is worse');
	assert.equal(cellRisk('peaHeat', c, 9, warming).score, -1);
	assert.equal(cellRisk('peaHeat', c, 9, warming).value, 1, 'probability capped at 1');
	assert.equal(cellRisk('peaHeat', c, 0.9, warming).score, 0, 'no change at the baseline warming');
	const comp = cellRisk('composite', c, 1.7, warming);
	assert.ok(comp.score < 0 && comp.value === undefined);
	assert.ok(Object.keys(RISKS).length === 6);
});

test('risk colours run red → amber → green', () => {
	const [r1, g1] = riskColor(-1), [r2, g2] = riskColor(1);
	assert.ok(r1 > g1 && g2 > r2);
	assert.deepEqual(riskColor(0), [236, 196, 94]);
});

test('outcomes: nothing without policies; peat and catch crops follow the active cards and decade', () => {
	const area = { contractPeatCo2e: 1000, organicContractHa: 40, peaSpinachHa: 100, peaSpinachCatchHa: 25 };
	const p = pricesAt(0.5, 2030, transition);
	assert.deepEqual(outcomes(new Set(), 2030, p, area), { peatCo2eAvoided: 0, peatHaOutOfCrops: 0, catchCropHaAdded: 0, dieselEurPerL: 0, fertiliserEurPerKgN: 0 });
	const nrl = outcomes(new Set(['eu_nature_restoration']), 2030, p, area);
	assert.equal(nrl.peatCo2eAvoided, 300);
	assert.equal(outcomes(new Set(['eu_nature_restoration']), 2050, p, area).peatCo2eAvoided, 500);
	assert.equal(outcomes(new Set(['eu_nature_restoration', 'fi_peat_ban']), 2030, p, area).peatHaOutOfCrops, 40, 'stricter rule wins');
	assert.equal(outcomes(new Set(['cap_catch_crops']), 2030, p, area).catchCropHaAdded, 75);
	const costs = outcomes(new Set(['eu_ets2', 'eu_cbam_fertiliser']), 2030, p, area);
	assert.ok(Math.abs(costs.dieselEurPerL - 0.0021 * 50) < 1e-12);
	assert.ok(Math.abs(costs.fertiliserEurPerKgN - 0.0037 * 150) < 1e-12);
});

test('area facts select parcels inside the polygon and weight risk by hectares', () => {
	const parcels = {
		lon: [22.1, 22.2, 25.0], lat: [61.0, 61.1, 61.0], area: [10, 30, 5],
		soil: ['organic', 'clay', 'organic'], crop: ['pea', 'spinach', 'pea'], catchCrop: [true, false, false],
		contract: [true, true, true], cell: ['A', 'B', 'A'], peatCo2e: [347, 0, 173]
	};
	const poly = { type: 'Polygon', coordinates: [[[22, 60.9], [22.5, 60.9], [22.5, 61.3], [22, 61.3], [22, 60.9]]] };
	const inside = areaFacts(parcels, poly);
	assert.equal(inside.parcels, 2);
	assert.equal(inside.contractPeatCo2e, 347);
	assert.equal(inside.organicContractHa, 10);
	assert.equal(inside.peaSpinachHa, 40);
	assert.equal(inside.peaSpinachCatchHa, 10);
	assert.equal(areaFacts(parcels, null).parcels, 3);
	const r = areaRisk('peaHeat', inside.cellHa, 0.9, warming);
	assert.ok(Math.abs(r.base - (0.1 * 10 + 0.3 * 30) / 40) < 1e-12, 'hectare-weighted baseline');
	assert.equal(areaRisk('peaHeat', new Map(), 1.5, warming), null);
});
