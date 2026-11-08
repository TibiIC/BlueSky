import { json } from '@sveltejs/kit';
import { z } from 'zod';
import { getDb } from '#lib/server/db.ts';
import type { RequestHandler } from './$types';

const body = z.object({
	itemKey: z.string().min(3).max(300),
	runId: z.string().min(1).max(40),
	choice: z.string().min(1).max(40),
	reviewer: z.string().trim().min(1, 'Your name is required').max(100)
});

/** POST: a person's choice for one flagged number. Appended to dev_decisions; the next pipeline run applies it. */
export const POST: RequestHandler = async ({ request }) => {
	const parsed = body.safeParse(await request.json().catch(() => null));
	if (!parsed.success) return json({ error: parsed.error.issues.map((i) => i.message).join('; ') }, { status: 400 });
	const db = await getDb().catch(() => null);
	if (!db) return json({ error: 'Database not configured. Set MONGODB_URI in frontend/.env.' }, { status: 503 });
	const item = await db.collection('dev_items').findOne({ itemKey: parsed.data.itemKey, runId: parsed.data.runId }, { projection: { options: 1 } });
	if (!item) return json({ error: 'No such item in that run' }, { status: 404 });
	if (!(item.options as { id: string }[]).some((o) => o.id === parsed.data.choice)) return json({ error: 'Not an option for this item' }, { status: 400 });
	const decision = { ...parsed.data, at: new Date().toISOString() };
	await db.collection('dev_decisions').insertOne({ ...decision });
	return json(decision, { status: 201 });
};
