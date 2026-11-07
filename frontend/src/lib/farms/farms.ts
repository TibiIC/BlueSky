import type { Color, PointPrimitive, PointPrimitiveCollection } from 'cesium';
import type { Globe } from '../globe/viewer.ts';
import type { Frame } from '../weather/terra.ts';

/** Apetit contract parcels on the globe: crop, soil, peat, soil-biodiversity proxy and crop water stress. */
export type FarmLayer = 'off' | 'crop' | 'soil' | 'peat' | 'bio' | 'stress_live' | 'stress_replay';

interface ParcelData {
	schema: string; source: string; crop_year: number;
	crop_codes: string[]; soil_codes: string[]; stress_crops: string[];
	cells: { id: string; lat: number; lon: number }[];
	biodiversity_note: string; peat_note: string; biodiversity_weights: Record<string, number>;
	parcels: {
		id: string[]; farm: string[]; lat: number[]; lon: number[]; area: number[]; region: string[];
		crop: number[]; soil: number[]; clay: number[]; peat: number[]; peat_misreported: number[];
		bio: number[]; rot: number[]; catch: number[]; organic_farm: number[]; drainage: string[]; cell: number[];
	};
}
interface Season { key: string; label: string; year: number; doy0: number; days: number; dims: number[]; data: string; bytes?: Uint8Array }

export interface RegionStats { stressedPct: number; meanStress: number; activeHa: number }
export interface ParcelInfo {
	id: string; farm: string; region: string; crop: string; soil: string; area: number; clay: number;
	peat: boolean; peatMisreported: boolean; bio: number; rotation: number; catchShare: number; organicFarm: boolean; drainage: string;
	stress: number | null;
}
export interface FarmStatus {
	loaded: boolean; error?: string; layer: FarmLayer; shown: number; total: number;
	peat: number; peatMisreported: number; peatHa: number;
	replay?: { key: string; label: string; date: string; day: number; days: number; playing: boolean; stats: Record<string, RegionStats> };
	live?: { simTime: string; stats: Record<string, RegionStats> };
	selected?: ParcelInfo;
	notes?: { biodiversity: string; peat: string; source: string };
}
export interface FarmFilter { crops: Set<string>; regions: Set<string>; peatOnly: boolean }

export const SEASONS: [string, string][] = [['2018', '2018 drought'], ['2026', '2026 season'], ['2050_ssp585', '2050 · SSP5-8.5']];
export const APETIT_CROPS = ['pea', 'turnip_rape', 'potato', 'carrot', 'spinach'];
const STRESS_CROP: Record<string, string> = { pea: 'pea', turnip_rape: 'turnip_rape', potato: 'potato', carrot: 'carrot', spinach: 'spinach', barley: 'cereal', wheat: 'cereal', oats: 'cereal', grass_ley: 'grass_ley' };

export const CROP_COLORS: Record<string, string> = {
	pea: '#7ee05a', turnip_rape: '#ffd60a', potato: '#d39a5c', carrot: '#ff7a1a', spinach: '#1fae6b',
	barley: '#bfae86', wheat: '#a8946a', oats: '#cfc8a2', grass_ley: '#5b8c6a', fallow: '#6b6b6b'
};
export const SOIL_COLORS: Record<string, string> = { clay: '#9b5d3a', silt: '#c49a5e', fine_sand: '#e0c77e', sand: '#f4e7b0', organic: '#3a2418' };
export const CROP_LABELS: Record<string, string> = { pea: 'Pea', turnip_rape: 'Turnip rape', potato: 'Potato', carrot: 'Carrot', spinach: 'Spinach', barley: 'Barley', wheat: 'Wheat', oats: 'Oats', grass_ley: 'Grass ley', fallow: 'Fallow' };
export const REGION_LABELS: Record<string, string> = { FI_SW: 'Finland · Säkylä', SE_SKANE: 'Sweden · Skåne/Halland' };

/** Stress ramp: green (no stress) to yellow to red (wilting). */
export function stressRgb(s: number): [number, number, number] {
	const t = Math.max(0, Math.min(1, s));
	const a: [number, number, number] = [46, 204, 113], b: [number, number, number] = [255, 214, 10], c: [number, number, number] = [230, 57, 70];
	const [p, q, u] = t < 0.5 ? [a, b, t * 2] : [b, c, (t - 0.5) * 2];
	return p.map((v, i) => Math.round(v + (q[i] - v) * u)) as [number, number, number];
}
/** Viridis-like ramp for the biodiversity proxy. */
export function bioRgb(v: number): [number, number, number] {
	const stops: [number, number, number][] = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
	const t = Math.max(0, Math.min(0.9999, v / 0.8)) * (stops.length - 1), i = Math.floor(t), f = t - i;
	return stops[i].map((x, k) => Math.round(x + (stops[i + 1][k] - x) * f)) as [number, number, number];
}

/** Validate generated files before indexing GPU points or replay arrays. */
export function validateParcels(d: ParcelData) {
 if(d?.schema!=='terra.apetit.parcels.v1'||!Array.isArray(d.parcels?.id)||!d.parcels.id.length||!Array.isArray(d.cells)||!d.cells.length)throw Error('Invalid parcel dataset');
 const p=d.parcels,n=p.id.length;
 for(const a of Object.values(p))if(!Array.isArray(a)||a.length!==n)throw Error('Parcel column length mismatch');
 for(let i=0;i<n;i++){
  if(!Number.isFinite(p.lat[i])||Math.abs(p.lat[i])>90||!Number.isFinite(p.lon[i])||Math.abs(p.lon[i])>180||!Number.isFinite(p.area[i])||p.area[i]<=0)throw Error('Invalid parcel coordinates or area');
  for(const [v,limit] of [[p.crop[i],d.crop_codes.length],[p.soil[i],d.soil_codes.length],[p.cell[i],d.cells.length]])if(!Number.isInteger(v)||v<0||v>=limit)throw Error('Invalid parcel index');
 }
}
export function validateSeason(s:Season,d:ParcelData,byteLength:number){
 const expected=[d.stress_crops.length,d.soil_codes.length,d.cells.length,s.days];
 if(!Number.isInteger(s.days)||s.days<1||s.days>366||!Array.isArray(s.dims)||s.dims.length!==4||s.dims.some((v,i)=>v!==expected[i])||expected.reduce((a,b)=>a*b,1)!==byteLength)throw Error('Season dimensions do not match parcel data');
}

export function attachFarms(globe: Globe, onStatus: (s: FarmStatus) => void) {
	const { C, viewer } = globe;
	const status: FarmStatus = { loaded: false, layer: 'off', shown: 0, total: 0, peat: 0, peatMisreported: 0, peatHa: 0 };
	const collection = viewer.scene.primitives.add(new C.PointPrimitiveCollection()) as PointPrimitiveCollection;
	collection.show = false;
	let data: ParcelData | null = null;
	let points: PointPrimitive[] = [];
	let stressIndex: Int16Array = new Int16Array(0); // index into season stress_crops, -1 = no crop
	let layer: FarmLayer = 'off';
	let filter: FarmFilter = { crops: new Set(Object.keys(CROP_COLORS)), regions: new Set(Object.keys(REGION_LABELS)), peatOnly: false };
	const seasons = new Map<string, Season>();
	let season: Season | null = null, day = 0, playing = false, speed = 5, lastTick = 0, raf = 0, lastPaint = 0;
	let liveFrame: Frame | null = null;
	let disposed = false;let seasonRequest=0;
	const css = (h: string, a = 1) => C.Color.fromCssColorString(h).withAlpha(a);
	const palette = {
		crop: Object.fromEntries(Object.entries(CROP_COLORS).map(([k, v]) => [k, css(v, APETIT_CROPS.includes(k) ? 0.95 : 0.55)])) as Record<string, Color>,
		soil: Object.fromEntries(Object.entries(SOIL_COLORS).map(([k, v]) => [k, css(v, 0.9)])) as Record<string, Color>,
		peatBad: css('#ff3b30'), peatOk: css('#ff9f0a'), mineral: css('#9aa5a8', 0.18), none: css('#7d8a8c', 0.15)
	};
	const scratch = new C.Color();
	const rgbColor = (rgb: [number, number, number], a = 0.95) => C.Color.fromBytes(rgb[0], rgb[1], rgb[2], Math.round(a * 255), scratch);
	const emit = () => onStatus({ ...status });

	function passes(i: number) {
		const p = data!.parcels;
		return filter.crops.has(data!.crop_codes[p.crop[i]]) && filter.regions.has(p.region[i]) && (!filter.peatOnly || p.peat[i] === 1);
	}
	function seasonStress(i: number, d: number): number | null {
		if (!season?.bytes) return null;
		const a = stressIndex[i]; if (a < 0) return null;
		const [, nSoil, nCell, nDay] = season.dims;
		const base = ((a * nSoil + data!.parcels.soil[i]) * nCell + data!.parcels.cell[i]) * nDay;
		const d0 = Math.max(0, Math.min(nDay - 1, Math.floor(d))), d1 = Math.min(nDay - 1, d0 + 1), f = d - Math.floor(d);
		const v0 = season.bytes[base + d0], v1 = season.bytes[base + d1];
		if (v0 === 0 && v1 === 0) return null;
		const s0 = v0 ? (v0 - 1) / 200 : 0, s1 = v1 ? (v1 - 1) / 200 : 0;
		return s0 + (s1 - s0) * f;
	}
	function liveStress(i: number): number | null {
		const f = liveFrame; const field = f?.fields.crop_stress; if (!f || f.ready===false || !field) return null;
		if (stressIndex[i] < 0) return null;
		const { nx, ny, west, east, south, north } = f.grid, p = data!.parcels;
		const ii = Math.round((p.lon[i] - west) / (east - west) * (nx - 1)), jj = Math.round((p.lat[i] - south) / (north - south) * (ny - 1));
		if (ii < 0 || jj < 0 || ii >= nx || jj >= ny) return null;
		const v = field[jj * nx + ii]; return v === null || v === undefined ? null : v;
	}
	function stressNow(i: number): number | null { return layer === 'stress_replay' ? seasonStress(i, day) : layer === 'stress_live' ? liveStress(i) : null; }

	function regionStats(get: (i: number) => number | null): Record<string, RegionStats> {
		const acc: Record<string, { ha: number; stressedHa: number; sum: number }> = {};
		const p = data!.parcels;
		for (let i = 0; i < points.length; i++) {
			if (!passes(i)||!APETIT_CROPS.includes(data!.crop_codes[p.crop[i]])) continue;
			const s = get(i); if (s === null) continue;
			const r = (acc[p.region[i]] ??= { ha: 0, stressedHa: 0, sum: 0 });
			r.ha += p.area[i]; r.sum += s * p.area[i]; if (s >= 0.5) r.stressedHa += p.area[i];
		}
		return Object.fromEntries(Object.entries(acc).map(([k, r]) => [k, { activeHa: r.ha, stressedPct: r.ha ? 100 * r.stressedHa / r.ha : 0, meanStress: r.ha ? r.sum / r.ha : 0 }]));
	}

	function paint() {
		if (!data) return;
		const p = data.parcels; let shown = 0;
		collection.show = layer !== 'off';
		for (let i = 0; i < points.length; i++) {
			const pt = points[i]; const ok = layer !== 'off' && passes(i);
			pt.show = ok; if (!ok) continue; shown++;
			const crop = data.crop_codes[p.crop[i]];
			if (layer === 'crop') pt.color = palette.crop[crop];
			else if (layer === 'soil') pt.color = palette.soil[data.soil_codes[p.soil[i]]];
			else if (layer === 'peat') pt.color = p.peat_misreported[i] ? palette.peatBad : p.peat[i] ? palette.peatOk : palette.mineral;
			else if (layer === 'bio') pt.color = rgbColor(bioRgb(p.bio[i]), 0.9);
			else { const s = stressNow(i); pt.color = s === null ? palette.none : rgbColor(stressRgb(s), 0.95); }
		}
		status.shown = shown;
		if (layer === 'stress_replay' && season) {
			const doy = season.doy0 + Math.floor(day);
			status.replay = { key: season.key, label: season.label, day, days: season.days, playing,
				date: new Date(Date.UTC(season.year, 0, 1) + (doy - 1) * 864e5).toISOString().slice(0, 10), stats: regionStats(i => seasonStress(i, day)) };
		}
		if (layer === 'stress_live' && liveFrame) status.live = { simTime: liveFrame.sim_time, stats: regionStats(liveStress) };
		if (status.selected) status.selected.stress = stressNow(data.parcels.id.indexOf(status.selected.id));
		emit();
	}

	function tick(now: number) {
		raf = 0; if (disposed || !playing || !season) return;
		const dt = lastTick ? Math.min(0.1, (now - lastTick) / 1000) : 0; lastTick = now;
		day += dt * speed;
		if (day >= season.days - 1) { day = season.days - 1; playing = false; }
		if (now - lastPaint > 45 || !playing) { lastPaint = now; paint(); }
		if (playing) raf = requestAnimationFrame(tick);
	}

	async function load() {
		try {
			const r = await fetch('/data/apetit/apetit_parcels.json'); if (!r.ok) throw Error(`Parcel data missing (${r.status}). Copy apetit_parcels.json into frontend/static/data/apetit/.`);
			const loaded=await r.json() as ParcelData;validateParcels(loaded);if(disposed)return;data=loaded;
			const p = data.parcels;
			stressIndex = Int16Array.from(p.crop.map(c => { const s = STRESS_CROP[data!.crop_codes[c]]; return s ? data!.stress_crops.indexOf(s) : -1; }));
			points = p.lat.map((lat, i) => collection.add({
				id: i, position: C.Cartesian3.fromDegrees(p.lon[i], lat, 16000),
				pixelSize: Math.min(9, 2.5 + Math.sqrt(p.area[i]) * 1.1),
				color: palette.none, // Elevated display points with depth testing: far-side parcels stay occluded.
				scaleByDistance: new C.NearFarScalar(1.5e4, 2.2, 1.5e6, 0.55)
			}));
			Object.assign(status, {
				loaded: true, total: points.length, peat: p.peat.reduce((a, b) => a + b, 0), peatMisreported: p.peat_misreported.reduce((a, b) => a + b, 0),
				peatHa: p.area.reduce((a, v, i) => a + (p.peat[i] ? v : 0), 0),
				notes: { biodiversity: data.biodiversity_note, peat: data.peat_note, source: data.source }
			});
			paint();
		} catch (e) { status.error = String(e); emit(); }
	}
	async function loadSeason(key: string) {
		if (!seasons.has(key)) {
			const r = await fetch(`/data/apetit/season_${key}.json`); if (!r.ok) throw Error(`Season ${key} missing (${r.status})`);
			const s = await r.json() as Season; const bin = atob(s.data); const bytes = new Uint8Array(bin.length);
			for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
			validateSeason(s,data!,bytes.length);if(bytes.some(v=>v>201))throw Error('Invalid stress byte');s.bytes = bytes; s.data = ''; seasons.set(key, s);
		}
		return seasons.get(key)!;
	}

	const handler = new C.ScreenSpaceEventHandler(viewer.scene.canvas);
	handler.setInputAction((e: { position: import('cesium').Cartesian2 }) => {
		if (!data || layer === 'off') return;
		const picked = viewer.scene.pick(e.position);
		if (!picked || picked.collection !== collection || typeof picked.id !== 'number') return;
		const i = picked.id as number, p = data.parcels;
		status.selected = {
			id: p.id[i], farm: p.farm[i], region: p.region[i], crop: data.crop_codes[p.crop[i]], soil: data.soil_codes[p.soil[i]], area: p.area[i], clay: p.clay[i],
			peat: p.peat[i] === 1, peatMisreported: p.peat_misreported[i] === 1, bio: p.bio[i], rotation: p.rot[i], catchShare: p.catch[i],
			organicFarm: p.organic_farm[i] === 1, drainage: p.drainage[i], stress: stressNow(i)
		};
		emit();
	}, C.ScreenSpaceEventType.LEFT_CLICK);

	load();
	return {
		setLayer(l: FarmLayer) { seasonRequest++;status.error=undefined;layer = l; status.layer = l; if (l !== 'stress_replay') { playing = false; status.replay = undefined; } if (l !== 'stress_live') status.live = undefined; paint(); },
		setFilter(f: FarmFilter) { filter = f; paint(); },
		/** Feed each live TERRA regional frame; parcels resample crop_stress immediately. */
		updateLive(frame: Frame | undefined) { if (!frame) return; liveFrame = frame; if (layer === 'stress_live') paint(); },
		async playSeason(key: string) {
			const request=++seasonRequest;
			try {
                if(!SEASONS.some(([k])=>k===key))throw Error('Unknown season');
                const loaded=await loadSeason(key);if(disposed||request!==seasonRequest)return;status.error=undefined;status.live=undefined;season=loaded; layer = 'stress_replay'; status.layer = layer; day = 0; playing = true; lastTick = 0;
				paint();if (!raf) raf = requestAnimationFrame(tick);
			} catch (e) { if(!disposed&&request===seasonRequest){status.error = String(e); emit();} }
		},
		togglePlay() { if (!season) return; if (day >= season.days - 1) day = 0; playing = !playing; lastTick = 0; if (playing && !raf) raf = requestAnimationFrame(tick); paint(); },
		seek(d: number) { if(!season)return;day = Math.max(0,Math.min(season.days-1,d)); paint(); },
		setSpeed(daysPerSecond: number) { speed = daysPerSecond; },
		clearSelection() { status.selected = undefined; emit(); },
		flyTo(region: 'FI_SW' | 'SE_SKANE') {
			const p=data?.parcels;const indices=p?p.id.map((_,i)=>i).filter(i=>p.region[i]===region):[];
            const [lon,lat]=p&&indices.length?[indices.reduce((a,i)=>a+p.lon[i],0)/indices.length,indices.reduce((a,i)=>a+p.lat[i],0)/indices.length]:region==='FI_SW'?[22.5,61]:[13.3,56];
			viewer.camera.flyTo({ destination: C.Cartesian3.fromDegrees(lon, lat, 150000), orientation: { heading: 0, pitch: C.Math.toRadians(-90), roll: 0 } });
		},
		destroy() { disposed = true;seasonRequest++; cancelAnimationFrame(raf); handler.destroy(); viewer.scene.primitives.remove(collection); }
	};
}
