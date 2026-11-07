import { json } from '@sveltejs/kit';
import { dbConfigured, getDb } from '#lib/server/db.ts';
import type { RequestHandler } from './$types';

/** Database status for the UI: not configured, reachable, or failing (with the reason). */
export const GET: RequestHandler = async () => {
	if (!dbConfigured()) return json({ configured: false, ok: false });
	try {
		const db = await getDb();
		await db!.command({ ping: 1 });
		return json({ configured: true, ok: true, database: db!.databaseName });
	} catch (e) {
		return json({ configured: true, ok: false, error: e instanceof Error ? e.message : String(e) });
	}
};
