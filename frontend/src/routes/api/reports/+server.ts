import { json } from '@sveltejs/kit';
import { getDb } from '#lib/server/db.ts';
import { saveReportInput, type ReportVersion, type Review } from '#lib/review/model.ts';
import type { RequestHandler } from './$types';

const unavailable = () => json({ error: 'Database not configured. Set MONGODB_URI in frontend/.env.' }, { status: 503 });

/** GET ?reportId=…: all saved versions (newest first) and the review log for one area. */
export const GET: RequestHandler = async ({ url }) => {
	const reportId = url.searchParams.get('reportId');
	if (!reportId) return json({ error: 'reportId is required' }, { status: 400 });
	const db = await getDb().catch(() => null);
	if (!db) return unavailable();
	const [versions, reviews] = await Promise.all([
		db.collection<ReportVersion>('reports').find({ reportId }, { projection: { _id: 0 } }).sort({ version: -1 }).toArray(),
		db.collection<Review>('reviews').find({ reportId }, { projection: { _id: 0 } }).sort({ at: 1 }).toArray()
	]);
	return json({ versions, reviews });
};

/** POST: save a new immutable version of an area report (starts as a draft). */
export const POST: RequestHandler = async ({ request }) => {
	const parsed = saveReportInput.safeParse(await request.json().catch(() => null));
	if (!parsed.success)
		return json({ error: 'Invalid report', issues: parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`) }, { status: 400 });
	const db = await getDb().catch(() => null);
	if (!db) return unavailable();
	const reports = db.collection<ReportVersion>('reports');
	const last = await reports.findOne({ reportId: parsed.data.reportId }, { sort: { version: -1 } });
	const doc: ReportVersion = { ...parsed.data, version: (last?.version ?? 0) + 1, status: 'draft', createdAt: new Date().toISOString() };
	await reports.insertOne({ ...doc });
	return json(doc, { status: 201 });
};
