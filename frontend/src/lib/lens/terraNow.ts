import type { Frame } from '../weather/terra.ts';
import type { LonLat } from '../geo/turf.ts';

/** Current conditions at a point, sampled from the TERRA regional frame (live forecast physics). */
export interface TerraNow {
	simTime: string;
	sourceMode: string;
	fetchedAt: string | null;
	historical: boolean;
	tempC: number | null;
	rainMmH: number | null;
	soilFraction: number | null;
	snowWaterMm: number | null;
}

const at = (f: Frame, key: string, n: number) => {
	const v = f.fields[key]?.[n];
	return typeof v === 'number' && Number.isFinite(v) ? v : null;
};

/**
 * Reads one snapshot from the TERRA bridge (`/terra/api/frame`) and samples the grid
 * node nearest the point. Returns null when TERRA is not running, not ready, or the
 * point is outside its Nordic grid. Never substitutes values.
 */
export async function terraNow(point: LonLat, signal?: AbortSignal): Promise<TerraNow | null> {
	try {
		const res = await fetch('/terra/api/frame', { signal: signal ?? AbortSignal.timeout(5000) });
		if (!res.ok) return null;
		const f = (await res.json()) as Frame;
		if (f.ready === false || !f.grid || !f.fields) return null;
		const { nx, ny, west, east, south, north } = f.grid;
		if (point.lon < west || point.lon > east || point.lat < south || point.lat > north) return null;
		const i = Math.round(((point.lon - west) / (east - west)) * (nx - 1));
		const j = Math.round(((point.lat - south) / (north - south)) * (ny - 1));
		const n = j * nx + i;
		const rain = at(f, 'precip_mm_h', n);
		return {
			simTime: f.sim_time,
			sourceMode: f.source.mode,
			fetchedAt: f.source.fetched_at,
			historical: f.timeline?.mode === 'historical',
			tempC: at(f, 'temp_c', n),
			rainMmH: rain === null ? null : rain * (f.controls.rain_scale ?? 1),
			soilFraction: at(f, 'soil_fraction', n),
			snowWaterMm: at(f, 'snow_water_mm', n)
		};
	} catch {
		return null;
	}
}
