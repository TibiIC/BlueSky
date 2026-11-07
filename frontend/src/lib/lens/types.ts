/**
 * Climate Lens report for a drawn area, computed on the server from the Apetit
 * package files built by `lens/build_data.py`. Every figure carries `src`: keys
 * into `LensReport.sources`, so the UI can show where it came from.
 */

export type Scenario = 'ssp126' | 'ssp245' | 'ssp585';
export type Decade = '2030s' | '2040s' | '2050s';
export const SCENARIOS: Scenario[] = ['ssp126', 'ssp245', 'ssp585'];
export const DECADES: Decade[] = ['2030s', '2040s', '2050s'];
export const SCENARIO_LABEL: Record<Scenario, string> = {
	ssp126: 'SSP1-2.6 · low emissions',
	ssp245: 'SSP2-4.5 · middle road',
	ssp585: 'SSP5-8.5 · high emissions'
};

export interface ClimateIndicators {
	/** Mean May–Aug temperature, °C. */
	tmeanMJJA: number;
	/** Days with Tmax ≥ 27 °C in June–July (pea flowering and pod fill). */
	hotDaysJJ: number;
	/** May–Aug precipitation, mm. */
	precipMJJA: number;
	/** May–Aug precipitation minus potential evapotranspiration, mm. */
	waterBalanceMJJA: number;
	/** Growing degree days above 5 °C, Apr–Sep. */
	gdd5: number;
	/** Days with Tmin < 0 °C in May (late frost). */
	frostDaysMay: number;
	/** Days with ≥ 20 mm rain in Jul–Sep (wet harvest). */
	heavyRainDaysJAS: number;
	/** Share of seasons with ≥ 8 hot days in June–July. */
	pHeatSeason: number;
	years: number;
}

export interface Figure {
	value: number;
	unit: string;
	src: string[];
}

export interface LensCatchment {
	id: string;
	water: string;
	status: string;
	pSensitivity: number;
	contractHaInArea: number;
	contractHaTotal: number;
	load?: { year: number; pKg: number; nKg: number };
	monitored: boolean;
}

export interface LensAction {
	id: string;
	name: string;
	flag: boolean;
	/** Why it applies to this area, with the computed figures it rests on. */
	evidence: string;
	/** Area-specific estimate where the package method allows one. */
	potential?: Figure;
	catalogue: { abatement2030: number; eurPerT: number | null; start: number; confidence: string | null; coBenefits: string | null; tradeOffs: string | null };
	src: string[];
}

export interface LensReport {
	available: true;
	notice: string;
	package: { name: string; version: string; builtAt: string; reportYear: number };
	area: {
		parcels: number;
		farms: number;
		farmsBySegment: Record<string, number>;
		hectares: Figure;
		contractHectares: Figure;
		cropHa: Record<string, number>;
		soilHa: Record<string, number>;
		regions: string[];
	};
	peat: {
		organicHa: Figure;
		organicContractHa: Figure;
		/** Drained-organic-soil CO2 + N2O on contract crops in the report year. */
		contractCo2e: Figure;
		allCropsCo2e: Figure;
		/** FI farms with ≥30 % of contract area on organic soil (soil map) whose survey says "Mineral soil". */
		misreportCandidates: { farm: string; organicShare: number; reported: string | null }[];
	};
	catchments: LensCatchment[];
	/** Null when the area contains no contract parcels. */
	climate: {
		cells: string[];
		baseline: ClimateIndicators;
		recent: ClimateIndicators;
		future: Record<Scenario, Record<Decade, ClimateIndicators>>;
		history: { years: number[]; hotDaysJJ: number[]; waterBalanceMJJA: number[] };
		src: string[];
	} | null;
	actions: LensAction[];
	prices: { year: number; items: Record<string, { eurPerT: number; replacementPremium: number }> };
	sources: Record<string, { path: string; sha256: string | null; label: string }>;
	constants: Record<string, unknown>;
}

export interface LensUnavailable {
	available: false;
	reason: string;
}

export type LensResult = LensReport | LensUnavailable;

/** Rough envelope of the package's contract parcels, for "outside coverage" hints. */
export const LENS_COVERAGE: [number, number, number, number] = [12.9, 55.5, 23.8, 61.6];
