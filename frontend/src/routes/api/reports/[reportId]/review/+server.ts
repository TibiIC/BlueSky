import { json } from '@sveltejs/kit';
import { getDb } from '#lib/server/db.ts';
import { nextStatus, reviewInput, type ReportVersion, type Review } from '#lib/review/model.ts';
import type { RequestHandler } from './$types';

/** POST: append an expert decision (approve, request changes, comment) to a report version. */
export const POST: RequestHandler = async ({ params, request }) => {
	const parsed = reviewInput.safeParse(await request.json().catch(() => null));
	if (!parsed.success)
		return json({ error: parsed.error.issues.map((i) => i.message).join('; ') }, { status: 400 });
	const db = await getDb().catch(() => null);
	if (!db) return json({ error: 'Database not configured. Set MONGODB_URI in frontend/.env.' }, { status: 503 });
	const reports = db.collection<ReportVersion>('reports');
	const target = await reports.findOne({ reportId: params.reportId, version: parsed.data.version });
	if (!target) return json({ error: 'No such report version' }, { status: 404 });
	const review: Review = { ...parsed.data, reportId: params.reportId, at: new Date().toISOString() };
	const status = nextStatus(target.status, parsed.data.action);
	await db.collection<Review>('reviews').insertOne({ ...review });
	if (status !== target.status) await reports.updateOne({ reportId: params.reportId, version: parsed.data.version }, { $set: { status } });
	return json({ review, status }, { status: 201 });
};
