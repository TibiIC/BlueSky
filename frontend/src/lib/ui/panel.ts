import { writable } from 'svelte/store';

/** Right-hand panel. Starts collapsed (globe first); selecting an area opens it on the Scenario tab. */
export const panelOpen = writable(false);

/** Which right-panel tab is open. Map layers follow it so tabs don't stack layers on the same fields. */
export type PanelTab = 'scenario' | 'area' | 'weather' | 'dev';
export const activeTab = writable<PanelTab>('scenario');
