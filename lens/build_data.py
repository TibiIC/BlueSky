"""Build the Climate Lens data files from the Apetit synthetic package.

Reads the unzipped APETIT_CLIMATE_NATURE_NAVIGATOR_2026 package and writes small,
deterministic JSON files to frontend/static/data/lens/. The frontend's
/api/selection route reads them to report on a drawn area.

Every derived number is computed here from package files; meta.json records the
package version, each source file's SHA-256 (from MANIFEST.json) and the
constants used, so figures in the UI can cite their origin.

Usage:
    python3 lens/build_data.py [--package PATH] [--out DIR]

PATH defaults to $APETIT_PACKAGE, then to ~/Downloads/Apetit_SinceAI2026 _1_/....
Requires pandas and pyarrow.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = Path.home() / 'Downloads/Apetit_SinceAI2026 _1_/Apetit_SinceAI2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026'
DEFAULT_OUT = REPO / 'frontend/static/data/lens'

REPORT_YEAR = 2025  # latest complete inventory year in the package
PLAN_YEAR = 2027  # planned crop shown in the SBTN screening review

# docs/METHODOLOGY.md §5 (Finnish GHG inventory; IPCC Wetlands Supplement), AR6 GWP100.
ORGANIC_CO2_T_HA = {'annual': 29.0, 'grass': 20.9}
ORGANIC_N2O_N_KG_HA = 13.0
N2O_GWP = 273
ORGANIC_N2O_T_CO2E_HA = ORGANIC_N2O_N_KG_HA * 44 / 28 * N2O_GWP / 1000

CONTRACT_CROPS = {'FI': {'pea', 'carrot', 'potato', 'spinach', 'turnip_rape'}, 'SE': {'pea'}}
ANNUAL_CROPS = {'barley', 'carrot', 'oats', 'pea', 'potato', 'spinach', 'turnip_rape', 'wheat'}

# Climate indicators. Thresholds follow docs/SIMULATION_DESIGN.md (GDD base 5 °C) and the
# FMI hot-day convention used in weather_monthly (Tmax >= 27 °C).
HOT_TMAX_C = 27.0
HEAVY_RAIN_MM = 20.0
BAD_HEAT_DAYS = 8  # Jun–Jul hot days at or above which a season counts as heat-stressed
PERIODS = {
    'baseline': ('historical', 1991, 2020),
    'recent': ('historical', 2012, 2026),
    '2030s': (None, 2031, 2040),
    '2040s': (None, 2041, 2050),
    '2050s': (None, 2051, 2060),
}
SCENARIOS = ['ssp126', 'ssp245', 'ssp585']

SOURCE_FILES = {
    'parcels': 'data/01_master/parcels.csv',
    'farms': 'data/01_master/farm_registry.csv',
    'cells': 'data/01_master/climate_grid_cells.csv',
    'crop_history': 'data/03_farming/parcel_crop_history_and_plan.csv',
    'farm_survey': 'data/03_farming/farm_survey_fi.csv',
    'calculator': 'data/03_farming/current_calculator_footprints.csv',
    'weather': 'data/04_climate/weather_daily_1991_2060.parquet',
    'catchments': 'data/06_nature/catchments.csv',
    'catchment_geo': 'data/06_nature/catchments.geojson',
    'loads': 'data/06_nature/monitored_catchment_loads.csv',
    'levers': 'data/05_scenarios/decarbonisation_levers.csv',
    'prices': 'data/05_scenarios/contract_prices_and_replacement_premiums.csv',
}


def r(x, nd=2):
    """Round floats for compact JSON; pass through None/NaN as None."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def write(out: Path, name: str, obj) -> None:
    path = out / name
    path.write_text(json.dumps(obj, separators=(',', ':'), ensure_ascii=False))
    print(f'  {name:<20} {path.stat().st_size / 1024:8.1f} KB')


def nearest_cells(lat: np.ndarray, lon: np.ndarray, cells: pd.DataFrame) -> np.ndarray:
    """Nearest 0.25° grid cell by equirectangular distance."""
    clat, clon = cells.lat.to_numpy(), cells.lon.to_numpy()
    k = np.cos(np.radians(lat))[:, None]
    d = (lat[:, None] - clat[None, :]) ** 2 + ((lon[:, None] - clon[None, :]) * k) ** 2
    return cells.cell_id.to_numpy()[d.argmin(axis=1)]


def build_parcels(pkg: Path, cells: pd.DataFrame):
    p = pd.read_csv(pkg / SOURCE_FILES['parcels'])
    farms = pd.read_csv(pkg / SOURCE_FILES['farms'])
    hist = pd.read_csv(pkg / SOURCE_FILES['crop_history'])
    h = hist[hist.year == REPORT_YEAR][['parcel_id', 'crop', 'catch_crop']]
    plan = hist[hist.year == PLAN_YEAR][['parcel_id', 'crop']].rename(columns={'crop': 'plan_crop'})
    p = p.merge(h, on='parcel_id', how='left').merge(plan, on='parcel_id', how='left').merge(farms[['farm_id', 'country', 'region']], on='farm_id')
    p['cell_id'] = nearest_cells(p.lat.to_numpy(), p.lon.to_numpy(), cells)

    organic = p.soil_class_soilmap.eq('organic')
    co2 = np.where(p.crop.eq('grass_ley'), ORGANIC_CO2_T_HA['grass'],
                   np.where(p.crop.isin(ANNUAL_CROPS), ORGANIC_CO2_T_HA['annual'], 0.0))
    p['peat_t_co2e'] = np.where(organic & (co2 > 0), (co2 + ORGANIC_N2O_T_CO2E_HA) * p.area_ha, 0.0)
    p['contract_crop'] = [c in CONTRACT_CROPS[k] for c, k in zip(p.crop, p.country)]

    cols = {
        'id': p.parcel_id.tolist(),
        'farm': p.farm_id.tolist(),
        'lon': [r(v, 5) for v in p.lon],
        'lat': [r(v, 5) for v in p.lat],
        'area': [r(v, 2) for v in p.area_ha],
        'soil': p.soil_class_soilmap.tolist(),
        'clay': [r(v, 0) for v in p.clay_pct_soilmap],
        'slope': [r(v, 1) for v in p.slope_pct],
        'distWater': p.dist_to_water_m.astype(int).tolist(),
        'drainage': p.drainage.tolist(),
        'catchment': p.catchment_id.tolist(),
        'pTest': [r(v, 1) for v in p.p_test_mgl_latest],
        'buffer': p.buffer_strip.astype(bool).tolist(),
        'crop': p.crop.fillna('').tolist(),
        'planCrop': p.plan_crop.fillna('').tolist(),
        'catchCrop': p.catch_crop.fillna(False).astype(bool).tolist(),
        'contract': p.contract_crop.tolist(),
        'cell': p.cell_id.tolist(),
        'peatCo2e': [r(v, 1) for v in p.peat_t_co2e],
    }
    return cols, p, farms


def build_farms(pkg: Path, parcels: pd.DataFrame, farms: pd.DataFrame):
    survey = pd.read_csv(pkg / SOURCE_FILES['farm_survey'])
    calc = pd.read_csv(pkg / SOURCE_FILES['calculator'])
    s = survey[survey.year == REPORT_YEAR]
    c = calc[calc.year == REPORT_YEAR]

    contract = parcels[parcels.contract_crop]
    share = contract.assign(org=contract.area_ha.where(contract.soil_class_soilmap.eq('organic'), 0.0)) \
        .groupby('farm_id')[['org', 'area_ha']].sum()
    share['organic_share'] = share.org / share.area_ha

    reported = s.groupby('farm_id').soil_type_reported.agg(lambda x: 'Organic soil' if (x == 'Organic soil').any() else x.iloc[0])
    out = {}
    for f in farms.itertuples():
        row = {
            'segment': f.segment,
            'region': f.region,
            'country': f.country,
            'organic': bool(f.organic_certified),
            'livestock': bool(f.livestock),
            'crops': f.contract_crops.split(';') if isinstance(f.contract_crops, str) else [],
            'contractHa': r(share.area_ha.get(f.farm_id), 2),
            'organicShare': r(share.organic_share.get(f.farm_id), 3),
            'soilReported': reported.get(f.farm_id),
        }
        fp = c[c.farm_id == f.farm_id]
        if len(fp):
            row['calculator'] = {k: r(v, 3) for k, v in zip(fp.crop, fp.carbon_footprint_kgco2e_per_kg)}
        sy = s[s.farm_id == f.farm_id]
        if len(sy):
            row['survey'] = [{'id': t.survey_id, 'crop': t.crop, 'yield': r(t.yield_t_ha, 2), 'irrigated': bool(t.irrigated),
                              'nMineral': r(t.n_mineral_kg_ha, 1), 'fertiliser': t.fertiliser_product} for t in sy.itertuples()]
        out[f.farm_id] = row
    return out


def build_catchments(pkg: Path, parcels: pd.DataFrame):
    meta = pd.read_csv(pkg / SOURCE_FILES['catchments']).set_index('catchment_id')
    loads = pd.read_csv(pkg / SOURCE_FILES['loads'])
    latest = loads[loads.year == loads.year.max()].set_index('catchment_id')
    contract_ha = parcels.groupby('catchment_id').area_ha.sum()
    gj = json.loads((pkg / SOURCE_FILES['catchment_geo']).read_text())
    gj.pop('crs', None)
    for feat in gj['features']:
        cid = feat['properties']['catchment_id']
        m = meta.loc[cid]
        props = {
            'id': cid,
            'region': m.region,
            'water': m.receiving_water_type,
            'status': m.ecological_status_class,
            'retention': r(m.nutrient_retention_frac_estimate, 3),
            'areaKm2': r(m.catchment_area_km2, 1),
            'fieldHa': r(m.field_area_total_ha, 0),
            'contractHa': r(contract_ha.get(cid, 0.0), 1),
            'pSensitivity': r(m.p_sensitivity, 2),
            'monitored': bool(m.monitoring_station),
        }
        if cid in latest.index:
            props['load'] = {'year': int(loads.year.max()), 'pKg': r(latest.loc[cid, 'total_p_load_kg'], 0),
                             'nKg': r(latest.loc[cid, 'total_n_load_kg'], 0)}
        feat['properties'] = props
        feat['geometry']['coordinates'] = [[[r(x, 4), r(y, 4)] for x, y in ring] for ring in feat['geometry']['coordinates']]
    return gj


def season_stats(w: pd.DataFrame) -> pd.DataFrame:
    """Per cell × scenario × year growing-season indicators from daily weather."""
    m, doy = w.date.dt.month, w.date.dt.dayofyear
    g = w.assign(
        year=w.date.dt.year,
        tmean_mjja=w.tmean_c.where(m.between(5, 8)),
        hot_jj=((w.tmax_c >= HOT_TMAX_C) & m.isin([6, 7])).astype(int),
        precip_mjja=w.precip_mm.where(m.between(5, 8), 0.0),
        pet_mjja=w.pet_mm.where(m.between(5, 8), 0.0),
        gdd5=np.clip(w.tmean_c - 5.0, 0, None).where(m.between(4, 9), 0.0),
        frost_may=((w.tmin_c < 0) & m.eq(5)).astype(int),
        heavy_jas=((w.precip_mm >= HEAVY_RAIN_MM) & m.isin([7, 8, 9])).astype(int),
        _doy=doy,
    ).groupby(['cell_id', 'scenario', 'year']).agg(
        tmean_mjja=('tmean_mjja', 'mean'), hot_jj=('hot_jj', 'sum'), precip_mjja=('precip_mjja', 'sum'),
        pet_mjja=('pet_mjja', 'sum'), gdd5=('gdd5', 'sum'), frost_may=('frost_may', 'sum'), heavy_jas=('heavy_jas', 'sum'),
    ).reset_index()
    g['water_balance'] = g.precip_mjja - g.pet_mjja
    return g


def summarise(g: pd.DataFrame) -> dict:
    return {
        'tmeanMJJA': r(g.tmean_mjja.mean(), 2),
        'hotDaysJJ': r(g.hot_jj.mean(), 2),
        'precipMJJA': r(g.precip_mjja.mean(), 1),
        'waterBalanceMJJA': r(g.water_balance.mean(), 1),
        'gdd5': r(g.gdd5.mean(), 0),
        'frostDaysMay': r(g.frost_may.mean(), 2),
        'heavyRainDaysJAS': r(g.heavy_jas.mean(), 2),
        'pHeatSeason': r((g.hot_jj >= BAD_HEAT_DAYS).mean(), 3),
        'years': int(g.year.nunique()),
    }


def build_climate(pkg: Path, cells: pd.DataFrame):
    w = pd.read_parquet(pkg / SOURCE_FILES['weather'], columns=['cell_id', 'date', 'tmean_c', 'tmax_c', 'tmin_c', 'precip_mm', 'pet_mm', 'scenario'])
    w['date'] = pd.to_datetime(w.date)
    g = season_stats(w)
    out = {}
    for cid, cg in g.groupby('cell_id'):
        cell = {'periods': {}, 'history': {}}
        for name, (scen, y0, y1) in PERIODS.items():
            sel = cg[cg.year.between(y0, y1)]
            if scen:
                cell['periods'][name] = summarise(sel[sel.scenario == scen])
            else:
                cell['periods'][name] = {s: summarise(sel[sel.scenario == s]) for s in SCENARIOS}
        hist = cg[(cg.scenario == 'historical') & cg.year.between(2012, 2026)].sort_values('year')
        cell['history'] = {'years': hist.year.tolist(), 'hotDaysJJ': hist.hot_jj.tolist(),
                           'waterBalanceMJJA': [r(v, 0) for v in hist.water_balance]}
        out[cid] = cell
    grid = [{'id': c.cell_id, 'region': c.region, 'lat': c.lat, 'lon': c.lon} for c in cells.itertuples()]
    return {'cells': grid, 'indicators': out}


# Global warming levels (°C above 1850–1900), IPCC AR6 WG1 SPM Table SPM.1 best estimates for
# 2021–2040 / 2041–2060 / 2081–2100, linearly interpolated to the decade centres used here.
# 1991–2020 is taken as 0.9 °C (AR6: 0.85 °C for 1995–2014).
GWL_BASELINE = 0.9
GWL_AR6 = {'ssp126': (1.5, 1.7, 1.8), 'ssp245': (1.5, 2.0, 2.7), 'ssp585': (1.6, 2.4, 4.4)}
GWL_CENTRES = (2030.5, 2050.5, 2090.5)
DECADE_CENTRES = {'2030s': 2035.5, '2040s': 2045.5, '2050s': 2055.5}
FIT_INDICATORS = ['hotDaysJJ', 'pHeatSeason', 'waterBalanceMJJA', 'heavyRainDaysJAS', 'frostDaysMay', 'gdd5', 'tmeanMJJA']


def gwl_at(scen: str, year: float) -> float:
    xs = (2005.5,) + GWL_CENTRES
    ys = (GWL_BASELINE,) + GWL_AR6[scen]
    return float(np.interp(year, xs, ys))


def build_warming(climate: dict) -> dict:
    """Per cell and indicator: slope of the indicator against global warming level.

    Ten points per fit (1991–2020 baseline + 3 SSPs × 3 decades). Using warming level
    instead of scenario labels smooths the single-realisation noise in each SSP run and
    lets the UI slide continuously between scenarios. The UI shows
    baseline + slope × (GWL − baseline GWL).
    """
    gwl = {s: {d: round(gwl_at(s, c), 3) for d, c in DECADE_CENTRES.items()} for s in SCENARIOS}
    cells = {}
    r2s = []
    for cid, cell in climate['indicators'].items():
        out = {}
        for k in FIT_INDICATORS:
            xs = [GWL_BASELINE] + [gwl[s][d] for s in SCENARIOS for d in DECADE_CENTRES]
            ys = [cell['periods']['baseline'][k]] + [cell['periods'][d][s][k] for s in SCENARIOS for d in DECADE_CENTRES]
            x, y = np.array(xs) - GWL_BASELINE, np.array(ys, dtype=float)
            slope, icpt = np.polyfit(x, y, 1)
            resid = y - (icpt + slope * x)
            ss = ((y - y.mean()) ** 2).sum()
            r2 = float(1 - (resid ** 2).sum() / ss) if ss > 0 else 1.0
            r2s.append(r2)
            out[k] = {'base': r(cell['periods']['baseline'][k], 3), 'slope': r(slope, 4), 'r2': r(r2, 2)}
        cells[cid] = out
    return {
        'baselineGwl': GWL_BASELINE,
        'gwl': gwl,
        'ar6': {'periods': ['2021-2040', '2041-2060', '2081-2100'], 'bestEstimate': GWL_AR6},
        'method': 'Linear fit of each indicator against global warming level across baseline + 9 SSP-decade points; '
                  'GWL from IPCC AR6 WG1 Table SPM.1 interpolated to decade centres.',
        'medianR2': r(float(np.median(r2s)), 2),
        'cells': cells,
    }


def build_transition(pkg: Path) -> dict:
    t = pd.read_csv(pkg / 'data/05_scenarios/transition_scenarios.csv')
    keep = ['current_policies', 'ndcs', 'below_2c', 'net_zero_2050']
    cols = {'carbon_price_eur_t': 'carbonPrice', 'eu_ets2_fuel_price_eur_t': 'ets2Price', 'n_fertiliser_price_index': 'nFertiliserIndex',
            'diesel_price_index': 'dieselIndex', 'electricity_price_eur_mwh': 'electricityPrice', 'frozen_veg_import_premium_pct': 'importPremiumPct'}
    out = {}
    for sc in keep:
        g = t[t.scenario == sc].sort_values('year')
        out[sc] = {'ssp': g.physical_pathway_proxy.iloc[0], 'years': g.year.astype(int).tolist(),
                   **{v: [r(x, 3) for x in g[k]] for k, v in cols.items()}}
    return {'scenarios': out, 'notice': 'Illustrative values in NGFS Phase V ranges (package transition_scenarios.csv).',
            'source': 'data/05_scenarios/transition_scenarios.csv'}


def build_levers(pkg: Path):
    lv = pd.read_csv(pkg / SOURCE_FILES['levers'])
    keep = lv[lv.lever_id.isin(['L08', 'L09', 'L10', 'L11', 'L12', 'L24'])]
    prices = pd.read_csv(pkg / SOURCE_FILES['prices'])
    latest = prices[prices.year == prices.year.max()]
    return {
        'levers': [{
            'id': t.lever_id, 'name': t.name, 'flag': bool(t.flag), 'type': t.lever_type,
            'abatement2030': int(t.abatement_tco2e_2030_design), 'capex': int(t.capex_eur),
            'opexPerYr': int(t.opex_delta_eur_per_yr), 'eurPerT': r(t.indicative_cost_eur_per_tco2e, 1),
            'start': int(t.earliest_start), 'rampYears': int(t.ramp_years),
            'confidence': None if pd.isna(t.confidence) else t.confidence,
            'coBenefits': None if pd.isna(t.co_benefits) else t.co_benefits,
            'tradeOffs': None if pd.isna(t.trade_offs) else t.trade_offs,
        } for t in keep.itertuples()],
        'prices': {'year': int(prices.year.max()),
                   'items': {t.item: {'eurPerT': r(t.contract_price_eur_t, 1), 'replacementPremium': r(t.replacement_import_premium_frac, 3)}
                             for t in latest.itertuples()}},
    }


def build_meta(pkg: Path):
    manifest = json.loads((pkg / 'MANIFEST.json').read_text())
    hashes = {f['path']: f['sha256'] for f in manifest.get('files', [])}
    return {
        'package': manifest.get('package'),
        'version': manifest.get('version'),
        'builtAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'reportYear': REPORT_YEAR,
        'synthetic': True,
        'notice': 'Synthetic data (Apetit Climate & Nature Navigator, Since AI ry 2026, CC BY 4.0). '
                  'Not Apetit\'s actual emissions or facts about real farms.',
        'sources': {k: {'path': v, 'sha256': hashes.get(v)} for k, v in SOURCE_FILES.items()},
        'constants': {
            'organicCo2TPerHa': ORGANIC_CO2_T_HA,
            'organicN2oNKgPerHa': ORGANIC_N2O_N_KG_HA,
            'organicN2oTCo2ePerHa': round(ORGANIC_N2O_T_CO2E_HA, 3),
            'n2oGwp': N2O_GWP,
            'hotDayTmaxC': HOT_TMAX_C,
            'heavyRainMm': HEAVY_RAIN_MM,
            'heatSeasonDays': BAD_HEAT_DAYS,
            'periods': {k: [v[1], v[2]] for k, v in PERIODS.items()},
            'contractCrops': {k: sorted(v) for k, v in CONTRACT_CROPS.items()},
        },
        'methodRefs': {
            'peat': 'docs/METHODOLOGY.md §5: drained organic soils 29.0 t CO2/ha/yr annual crops (20.9 grass) + 13 kg N2O-N/ha/yr',
            'soilMap': 'parcels.csv soil_class_soilmap is ~88 % accurate (docs/NATURE_SBTN.md)',
            'climate': 'Indicators computed from weather_daily_1991_2060.parquet; historical to 2026, then SSP runs (one realisation each)',
            'priority': 'docs/NATURE_SBTN.md D1 formula: (P/median(P) + 0.5 N/median(N)) × state_weight × p_sensitivity',
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--package', type=Path, default=Path(os.environ.get('APETIT_PACKAGE', DEFAULT_PACKAGE)))
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    pkg: Path = args.package
    if not (pkg / 'MANIFEST.json').exists():
        raise SystemExit(f'Package not found at {pkg} (set --package or APETIT_PACKAGE)')
    args.out.mkdir(parents=True, exist_ok=True)

    print(f'Reading {pkg}')
    cells = pd.read_csv(pkg / SOURCE_FILES['cells'])
    parcel_cols, parcels, farms = build_parcels(pkg, cells)
    print(f'Writing {args.out}')
    write(args.out, 'parcels.json', parcel_cols)
    write(args.out, 'farms.json', build_farms(pkg, parcels, farms))
    write(args.out, 'catchments.geojson', build_catchments(pkg, parcels))
    climate = build_climate(pkg, cells)
    write(args.out, 'climate.json', climate)
    write(args.out, 'warming.json', build_warming(climate))
    write(args.out, 'transition.json', build_transition(pkg))
    write(args.out, 'levers.json', build_levers(pkg))
    write(args.out, 'meta.json', build_meta(pkg))


if __name__ == '__main__':
    main()
