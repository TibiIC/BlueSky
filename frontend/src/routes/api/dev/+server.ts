import { json } from '@sveltejs/kit';
import { getDb } from '#lib/server/db.ts';
import type { RequestHandler } from './$types';

/**
 * GET: the latest curation run (method, per-series noise, scores, totals, scatter points), every
 * flagged number ranked by tonnes of CO2 at stake, and the latest decision a person made on each.
 */
export const GET: RequestHandler = async () => {
	const db = await getDb().catch(() => null);
	if (!db) return json({ error: 'Database not configured. Set MONGODB_URI in frontend/.env.' }, { status: 503 });
	const run = await db.collection('dev_runs').find({}, { projection: { _id: 0 } }).sort({ runAt: -1 }).limit(1).next();
	if (!run) return json({ error: 'No curation run yet. Run python3 -m quality.pipeline && python3 -m quality.publish_mongo.' }, { status: 404 });
	const items = await db
		.collection('dev_items')
		.find({ runId: run.runId }, { projection: { _id: 0 } })
		.sort({ at_stake: -1, record_key: 1 })
		.toArray();
	const decisions = await db
		.collection('dev_decisions')
		.aggregate([{ $sort: { at: 1 } }, { $group: { _id: '$itemKey', last: { $last: '$$ROOT' } } }])
		.toArray();
	return json({
		run,
		items,
		decisions: Object.fromEntries(decisions.map((d) => [d._id, { choice: d.last.choice, reviewer: d.last.reviewer, at: d.last.at }]))
	});
};
