import type { Viewer } from 'cesium';
import type { CesiumModule } from './cesium.ts';

/** Rank 1: capitals, visible from far out. Rank 3: appears only when zoomed in. */
interface City {
	name: string;
	lon: number;
	lat: number;
	rank: 1 | 2 | 3;
}

export const CITIES: City[] = [
	// Finland
	{ name: 'Helsinki', lon: 24.9384, lat: 60.1699, rank: 1 },
	{ name: 'Espoo', lon: 24.6559, lat: 60.2055, rank: 3 },
	{ name: 'Tampere', lon: 23.761, lat: 61.4978, rank: 2 },
	{ name: 'Vantaa', lon: 25.0378, lat: 60.2934, rank: 3 },
	{ name: 'Turku', lon: 22.2666, lat: 60.4518, rank: 2 },
	{ name: 'Oulu', lon: 25.4651, lat: 65.0121, rank: 2 },
	{ name: 'Jyväskylä', lon: 25.7473, lat: 62.2426, rank: 2 },
	{ name: 'Kuopio', lon: 27.677, lat: 62.8924, rank: 2 },
	{ name: 'Lahti', lon: 25.6612, lat: 60.9827, rank: 3 },
	{ name: 'Pori', lon: 21.7974, lat: 61.4851, rank: 3 },
	{ name: 'Vaasa', lon: 21.6165, lat: 63.0951, rank: 2 },
	{ name: 'Seinäjoki', lon: 22.8403, lat: 62.7903, rank: 3 },
	{ name: 'Joensuu', lon: 29.7636, lat: 62.601, rank: 3 },
	{ name: 'Rovaniemi', lon: 25.7294, lat: 66.5039, rank: 2 },
	// Sweden
	{ name: 'Stockholm', lon: 18.0686, lat: 59.3293, rank: 1 },
	{ name: 'Gothenburg', lon: 11.9746, lat: 57.7089, rank: 2 },
	{ name: 'Malmö', lon: 13.0038, lat: 55.605, rank: 2 },
	{ name: 'Uppsala', lon: 17.6389, lat: 59.8586, rank: 3 },
	{ name: 'Västerås', lon: 16.5448, lat: 59.6099, rank: 3 },
	{ name: 'Örebro', lon: 15.2134, lat: 59.2753, rank: 3 },
	{ name: 'Linköping', lon: 15.6214, lat: 58.4108, rank: 3 },
	{ name: 'Helsingborg', lon: 12.6945, lat: 56.0465, rank: 3 },
	{ name: 'Jönköping', lon: 14.1618, lat: 57.7826, rank: 3 },
	{ name: 'Norrköping', lon: 16.1924, lat: 58.5877, rank: 3 },
	{ name: 'Umeå', lon: 20.263, lat: 63.8258, rank: 2 },
	{ name: 'Gävle', lon: 17.1413, lat: 60.6749, rank: 3 },
	{ name: 'Sundsvall', lon: 17.3069, lat: 62.3908, rank: 3 },
	{ name: 'Luleå', lon: 22.1547, lat: 65.5848, rank: 2 },
	{ name: 'Kiruna', lon: 20.2253, lat: 67.8558, rank: 2 }
];

/** Camera distance (m) beyond which a label is hidden, per rank. */
const FAR: Record<City['rank'], number> = { 1: 7_000_000, 2: 2_600_000, 3: 900_000 };

/** City labels that fade in as the camera gets closer. */
export function addCityLabels(C: CesiumModule, viewer: Viewer) {
	const outline = C.Color.fromCssColorString('#0b1020');
	const source = new C.CustomDataSource('cities');

	for (const city of CITIES) {
		const far = FAR[city.rank];
		const visible = new C.DistanceDisplayCondition(0, far);
		const fade = new C.NearFarScalar(far * 0.55, 1, far, 0);
		source.entities.add({
			name: city.name,
			position: C.Cartesian3.fromDegrees(city.lon, city.lat, 30),
			point: {
				pixelSize: city.rank === 1 ? 6 : 4,
				color: C.Color.WHITE,
				outlineColor: outline,
				outlineWidth: 1.5,
				distanceDisplayCondition: visible,
				translucencyByDistance: fade,
				disableDepthTestDistance: Number.POSITIVE_INFINITY
			},
			label: {
				text: city.name,
				font: `${city.rank === 1 ? 600 : 500} ${city.rank === 1 ? 16 : 14}px "Inter", system-ui, -apple-system, "Segoe UI", sans-serif`,
				fillColor: C.Color.WHITE,
				outlineColor: outline,
				outlineWidth: 3,
				style: C.LabelStyle.FILL_AND_OUTLINE,
				verticalOrigin: C.VerticalOrigin.BOTTOM,
				pixelOffset: new C.Cartesian2(0, -7),
				distanceDisplayCondition: visible,
				translucencyByDistance: fade,
				disableDepthTestDistance: Number.POSITIVE_INFINITY
			}
		});
	}

	viewer.dataSources.add(source);
	return source;
}
