import { json } from '@sveltejs/kit';
import { z } from 'zod';
import { getDb } from '#lib/server/db.ts';
import type { RequestHandler } from './$types';

const body = z
	.object({
		findingKey: z.string().min(3).max(300),
		runId: z.string().min(1).max(40),
		decision: z.enum(['approve', 'reject']),
		reviewer: z.string().trim().min(1, 'Reviewer name is required').max(100),
		comment: z.string().trim().max(2000).default('')
	})
	.refine((b) => b.decision !== 'reject' || b.comment.length > 0, { message: 'Say why it is rejected', path: ['comment'] });

/** POST: an expert's decision on a data-quality finding. Appended to dq_reviews, never edited. */
export const POST: RequestHandler = async ({ request }) => {
	const parsed = body.safeParse(await request.json().catch(() => null));
	if (!parsed.success) return json({ error: parsed.error.issues.map((i) => i.message).join('; ') }, { status: 400 });
	const db = await getDb().catch(() => null);
	if (!db) return json({ error: 'Database not configured. Set MONGODB_URI in frontend/.env.' }, { status: 503 });
	const exists = await db.collection('dq_findings').findOne({ findingKey: parsed.data.findingKey, runId: parsed.data.runId }, { projection: { _id: 1 } });
	if (!exists) return json({ error: 'No such finding in that run' }, { status: 404 });
	const review = { ...parsed.data, level: 'G', at: new Date().toISOString() };
	await db.collection('dq_reviews').insertOne({ ...review });
	return json(review, { status: 201 });
};
