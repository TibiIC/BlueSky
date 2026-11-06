import { writable } from 'svelte/store';

export interface TilesState {
	/** loading: tileset being created; ready: can be toggled; unavailable: no key or failed. */
	status: 'loading' | 'ready' | 'unavailable';
	enabled: boolean;
	reason?: string;
}

export const tilesState = writable<TilesState>({ status: 'loading', enabled: false });

export interface ImageryState {
	world: 'ion' | 'keyless' | null;
	finlandOrthophoto: boolean;
}

export const imageryState = writable<ImageryState>({ world: null, finlandOrthophoto: false });
