import { json } from '@sveltejs/kit';
import { getDb } from '#lib/server/db.ts';
import type { RequestHandler } from './$types';

const QUEUE_FIELDS = {
	_id: 0, record_key: 1, issue_type: 1, table: 1, year: 1, rule: 1, evidence: 1, field: 1, observed: 1, proposed: 1,
	action: 1, confidence: 1, level: 1, sources: 1, hypotheses: 1, impact_tco2e: 1, status: 1, priority: 1, ai: 1, findingKey: 1,
	'locator.status_reason': 1, 'locator.scope': 1, 'locator.in_estimate': 1
};

/**
 * GET: the latest data-quality run (scores, counts, inventory range), its review queue ranked by
 * |impact| x (1 - confidence), the latest expert decision on each queued finding, and the
 * legitimate look-alikes grouped by reason. ?status=confirmed|proposed|needs_review|unexplained
 * lists findings of that status instead of the queue.
 */
export const GET: RequestHandler = async ({ url }) => {
	const db = await getDb().catch(() => null);
	if (!db) return json({ error: 'Database not configured. Set MONGODB_URI in frontend/.env.' }, { status: 503 });
	const run = await db.collection('dq_runs').find({}, { projection: { _id: 0 } }).sort({ runAt: -1 }).limit(1).next();
	if (!run) return json({ error: 'No data-quality run published yet. Run python3 -m quality.pipeline && python3 -m quality.publish_mongo.' }, { status: 404 });
	const status = url.searchParams.get('status');
	const filter = status
		? { runId: run.runId, status }
		: { runId: run.runId, status: { $in: ['needs_review', 'proposed', 'unexplained'] } };
	const [findings, checked, inventory] = await Promise.all([
		db.collection('dq_findings').find(filter, { projection: QUEUE_FIELDS }).sort({ priority: -1, record_key: 1 }).limit(Number(url.searchParams.get('limit') ?? 40)).toArray(),
		db.collection('dq_checked').aggregate([{ $match: { runId: run.runId } }, { $group: { _id: { $arrayElemAt: [{ $split: ['$reason', ':'] }, 0] }, n: { $sum: 1 } } }, { $sort: { n: -1 } }]).toArray(),
		db.collection('inventory').find({ runId: run.runId, scope: 'total' }, { projection: { _id: 0 } }).toArray()
	]);
	const keys = findings.map((f) => f.findingKey);
	const decisions = await db
		.collection('dq_reviews')
		.aggregate([{ $match: { findingKey: { $in: keys } } }, { $sort: { at: 1 } }, { $group: { _id: '$findingKey', last: { $last: '$$ROOT' } } }])
		.toArray();
	return json({
		run,
		findings,
		decisions: Object.fromEntries(decisions.map((d) => [d._id, { decision: d.last.decision, reviewer: d.last.reviewer, comment: d.last.comment, at: d.last.at }])),
		checked: checked.map((c) => ({ reason: c._id, count: c.n })),
		inventory
	});
};
