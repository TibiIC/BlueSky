import { writable } from 'svelte/store';
import type { RiskId } from './engine.ts';

export interface PolicyState {
	/** Ids of switched-on policy cards. */
	active: Set<string>;
	year: number;
	risk: RiskId;
	showMap: boolean;
	/** The most recent toggle and how much it moved global warming in `year`, for the meter. */
	lastChange: { title: string; on: boolean; deltaC: number } | null;
}

export const policyState = writable<PolicyState>({
	active: new Set(),
	year: 2050,
	risk: 'composite',
	showMap: true,
	lastChange: null
});
