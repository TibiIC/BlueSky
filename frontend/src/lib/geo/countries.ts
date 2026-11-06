import type { Feature, MultiPolygon, Polygon } from 'geojson';
import { bbox, booleanIntersects } from '@turf/turf';
import nordic from './data/nordic-countries.json' with { type: 'json' };

/** Natural Earth 1:50m outlines of Finland (incl. Åland) and Sweden. */
type CountryFeature = Feature<MultiPolygon, { name: string; iso: string }>;

const countries = (nordic.features as CountryFeature[]).map((feature) => ({
	feature,
	bbox: bbox(feature)
}));

/** Names of the countries (Finland, Sweden) that the polygon touches or overlaps. */
export function intersectingCountries(geometry: Polygon): string[] {
	const [w, s, e, n] = bbox(geometry);
	return countries
		.filter(({ bbox: [cw, cs, ce, cn] }) => w <= ce && e >= cw && s <= cn && n >= cs)
		.filter(({ feature }) => booleanIntersects(geometry, feature))
		.map(({ feature }) => feature.properties.name);
}
