/** Bounding box as [west, south, east, north] in degrees. */
export type LonLatBox = [west: number, south: number, east: number, north: number];

/** Finland + Sweden: the area where street-level zoom and detailed tiles are allowed. */
export const NORDIC_BOX: LonLatBox = [10.5, 55.0, 31.6, 70.1];

/** Finland incl. Åland, used to limit the NLS orthophoto layer. */
export const FINLAND_BOX: LonLatBox = [19.0, 59.3, 31.6, 70.1];

/** Centre of the initial Finland + Sweden view. */
export const NORDIC_CENTER = { lon: 20.5, lat: 62.3 };

/** Static Natural Earth 1:50m land boundary lines (served from /static). */
export const BORDERS_URL = '/data/borders.geojson';
