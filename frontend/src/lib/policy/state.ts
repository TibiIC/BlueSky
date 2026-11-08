import { writable } from 'svelte/store';
import { DEFAULT_COMPLIANCE, type RiskId } from './engine.ts';

export interface PolicyState {
	/** Ids of switched-on policy cards. */
	active: Set<string>;
	year: number;
	risk: RiskId;
	showMap: boolean;
	/** Farmer compliance with the Finland & EU rules, 0–1. */
	compliance: number;
	/** The most recent toggle and how much it moved global warming in `year`, for the meter. */
	lastChange: { title: string; on: boolean; deltaC: number } | null;
}

export const policyState = writable<PolicyState>({
	active: new Set(),
	year: 2050,
	risk: 'composite',
	showMap: true,
	compliance: DEFAULT_COMPLIANCE,
	lastChange: null
});
