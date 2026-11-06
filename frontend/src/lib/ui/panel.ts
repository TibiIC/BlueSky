import { writable } from 'svelte/store';

/** Right-hand panel (future "Problems / Effects / Solutions / Impact"). Hidden by default. */
export const panelOpen = writable(false);
