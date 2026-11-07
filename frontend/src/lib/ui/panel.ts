import { writable } from 'svelte/store';

/** Right-hand panel (Scenario + Area report). Open by default: it is the main control surface. */
export const panelOpen = writable(true);

/** Which right-panel tab is open. Map layers follow it so tabs don't stack layers on the same fields. */
export type PanelTab = 'scenario' | 'area' | 'weather' | 'quality';
export const activeTab = writable<PanelTab>('scenario');
