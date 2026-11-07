/**
 * Evidence catalogue: every dataset the app can draw on, including the ones kept off the
 * screen. The report agent (pinned for later) builds its evidence bundle from this list,
 * so details hidden to keep the UI simple still reach the generated report, with their caveats.
 *
 * `onScreen` says whether the UI currently shows it; `useInReport` says whether reports should
 * cite it. Caveats travel with every item and must be quoted when the item is used.
 */

export type EvidenceKind = 'synthetic-package' | 'model' | 'public-measured' | 'public-model' | 'proxy' | 'policy';

export interface EvidenceSource {
	id: string;
	label: string;
	kind: EvidenceKind;
	/** Where the app reads it: a static file or an API route. */
	location: string;
	/** Script that regenerates it, if any. */
	builtBy?: string;
	onScreen: boolean;
	useInReport: boolean;
	/** What it can support in a report. */
	supports: string;
	/** Must accompany any use. */
	caveat: string;
	source: string;
}

export const EVIDENCE: EvidenceSource[] = [
	// Apetit package (synthetic), Climate Lens build
	{
		id: 'lens.parcels',
		label: 'Contract parcels: soil map, crop 2025, peat emissions, catchment',
		kind: 'synthetic-package',
		location: '/data/lens/parcels.json',
		builtBy: 'lens/build_data.py',
		onScreen: true,
		useInReport: true,
		supports: 'Area facts, peat emissions under Apetit crops, soil-misreport candidates',
		caveat: 'Synthetic parcels; soil map ~88 % accurate; peat factor 29 t CO₂/ha/yr (METHODOLOGY §5).',
		source: 'Apetit Climate & Nature Navigator synthetic dataset, Since AI ry 2026 (CC BY 4.0)'
	},
	{
		id: 'lens.climate',
		label: 'Growing-season indicators 1991–2060 by SSP, and warming-level fits',
		kind: 'synthetic-package',
		location: '/data/lens/climate.json, /data/lens/warming.json',
		builtBy: 'lens/build_data.py',
		onScreen: true,
		useInReport: true,
		supports: 'Pea heat, drought, wet harvest, season length, late frost by scenario and decade',
		caveat: 'One synthetic realisation per SSP; drought and wet-harvest signals are low confidence (fit R² ≈ 0.05).',
		source: 'Package weather_daily_1991_2060; IPCC AR6 WG1 Table SPM.1 warming levels'
	},
	{
		id: 'lens.levers',
		label: 'Decarbonisation levers and contract prices',
		kind: 'synthetic-package',
		location: '/data/lens/levers.json, /data/lens/transition.json',
		builtBy: 'lens/build_data.py',
		onScreen: true,
		useInReport: true,
		supports: 'Actions with abatement and €/t; carbon, fertiliser and diesel prices by scenario',
		caveat: 'Lever abatement and costs are design estimates; prices are illustrative NGFS-range values.',
		source: 'Package decarbonisation_levers.csv, transition_scenarios.csv'
	},
	{
		id: 'policy.cards',
		label: 'Policy cards and warming-meter weights',
		kind: 'policy',
		location: 'src/lib/policy/policies.json',
		onScreen: true,
		useInReport: true,
		supports: 'Which policies are assumed, their status and effects',
		caveat: 'Illustrative weights (approximate emission shares); a planning aid, not a policy model.',
		source: 'Sources listed per card'
	},
	// Andrew's TERRA additions
	{
		id: 'terra.farms',
		label: 'Parcel crops 2026, soil class, peat flags',
		kind: 'synthetic-package',
		location: '/data/apetit/apetit_parcels.json',
		builtBy: 'terra/apetit/build_farm_layers.py',
		onScreen: true,
		useInReport: true,
		supports: 'Crop mix and peat mismatch counts per area',
		caveat: 'Synthetic parcels; a soil/report mismatch is not proof of misreporting.',
		source: 'Apetit synthetic dataset (CC BY 4.0)'
	},
	{
		id: 'terra.season-replay',
		label: 'Season replays: FAO-56 crop water stress, 2018, 2026, 2050 SSP5-8.5',
		kind: 'model',
		location: '/data/apetit/season_2018.json, season_2026.json, season_2050_ssp585.json',
		builtBy: 'terra/apetit/build_farm_layers.py',
		onScreen: true,
		useInReport: true,
		supports: 'How water stress builds through a drought season, and in a 2050 high-warming season',
		caveat: 'Synthetic daily weather; generic spring-crop calendars, root depths and soil capacities; not measured damage.',
		source: 'Package weather; FAO-56 crop water stress'
	},
	{
		id: 'terra.microbiome-proxy',
		label: 'Soil-biodiversity proxy from management (rotation, catch crops, organic farming)',
		kind: 'proxy',
		location: '/data/apetit/apetit_parcels.json (bio field)',
		builtBy: 'terra/apetit/build_farm_layers.py',
		onScreen: false,
		useInReport: true,
		supports: 'Qualitative note on management practices that favour soil life',
		caveat: 'NOT MEASURED. No microbial sampling; a management-based habitat indicator only. Never present as microbial diversity.',
		source: 'Derived from synthetic parcel management fields'
	},
	{
		id: 'terra.soil-biology',
		label: 'Measured soil biology: Kungsängen fungal DNA (SE), Karstula enzymes (FI)',
		kind: 'public-measured',
		location: '/data/biology/kungsangen.json, /data/biology/karstula.json',
		builtBy: 'terra/biology/build_measured.py, terra/biology/build_finland.py',
		onScreen: true,
		useInReport: true,
		supports: 'Context on what measured soil biology looks like; an SBTN monitoring path',
		caveat: 'Two single study sites far from Apetit parcels; different methods; no farm interpolation or ranking.',
		source: 'Rosling et al. 2026 (GBIF, CC0); Adamczyk et al. 2025 (Zenodo, CC BY 4.0)'
	},
	{
		id: 'terra.cmip6-crosscheck',
		label: 'Real climate-model cross-check for Säkylä and Bjuv (two CMIP6 HighResMIP models)',
		kind: 'public-model',
		location: '/data/decision/evidence.json (climate)',
		builtBy: 'terra/research/build_decision_data.py',
		onScreen: true,
		useInReport: true,
		supports: 'Whether the synthetic scenarios point the same way as real projections',
		caveat: 'Two models, ten-year windows, near-RCP8.5 family; not a multi-SSP ensemble.',
		source: 'Open-Meteo climate API (CMIP6 HighResMIP)'
	},
	{
		id: 'terra.benchmark-2018',
		label: '2018 soil-water benchmark against ERA5-Land',
		kind: 'public-model',
		location: '/data/decision/evidence.json (benchmark)',
		builtBy: 'terra/research/build_decision_data.py',
		onScreen: true,
		useInReport: true,
		supports: 'How the land model tracks a reanalysis through the 2018 drought',
		caveat: 'Reanalysis comparison, not independent observational validation.',
		source: 'ERA5 / ERA5-Land via Open-Meteo'
	},
	{
		id: 'terra.supply-screen',
		label: 'Supply screen: shipment modes, 2026 crop prices, replacement premium',
		kind: 'synthetic-package',
		location: '/data/decision/evidence.json (supply)',
		builtBy: 'terra/research/build_decision_data.py',
		onScreen: true,
		useInReport: true,
		supports: 'Cost of covering a shortfall with imports',
		caveat: 'Shortfall and adaptation cost are user-entered assumptions; no route-level or ROI inference.',
		source: 'Package shipments and contract prices'
	},
	{
		id: 'terra.hydrology',
		label: 'Real basins and rivers (HydroBASINS L5, HydroRIVERS) with downstream routing',
		kind: 'public-measured',
		location: '/data/hydrology/network.json',
		builtBy: 'terra/hydrology/build_network.py',
		onScreen: true,
		useInReport: true,
		supports: 'Where an area drains to downstream; real-geography upgrade path for SBTN freshwater',
		caveat: 'Generalised geometry; modeled runoff contribution, not gauged discharge; not the synthetic catchments used for D1.',
		source: 'WWF HydroSHEDS, Lehner & Grill 2013 (https://www.hydrosheds.org)'
	},
	{
		id: 'terra.stress-experiments',
		label: 'Short regional stress experiments (up to 168 h, temperature/rain/evaporation offsets)',
		kind: 'model',
		location: 'POST /terra/api/scenario',
		onScreen: false,
		useInReport: false,
		supports: 'Short-term soil-water sensitivity only',
		caveat: 'Hours, not climate; independent of circulation. Kept off screen and out of reports to avoid mixing with decadal scenarios.',
		source: 'TERRA regional land model'
	},
	{
		id: 'terra.live',
		label: 'Live forecast-driven soil water, snow, rain and wind',
		kind: 'model',
		location: 'GET /terra/api/frame',
		onScreen: true,
		useInReport: true,
		supports: 'Current conditions in an area (this week, not decades)',
		caveat: 'Open-Meteo forecasts, not observations; uncalibrated land parameters.',
		source: 'Open-Meteo (CC BY 4.0); TERRA regional physics'
	}
];

/** Sources a report may cite, with their caveats. */
export const reportEvidence = () => EVIDENCE.filter((e) => e.useInReport);
