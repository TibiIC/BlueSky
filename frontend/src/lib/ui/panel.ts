import { writable } from 'svelte/store';

/** Right-hand panel (Scenario + Area report). Open by default: it is the main control surface. */
export const panelOpen = writable(true);
