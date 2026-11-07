import test from 'node:test';
import assert from 'node:assert/strict';
import { nextStatus, reviewInput, saveReportInput } from '../src/lib/review/model.ts';

test('review status: approve and request changes move it, comments do not', () => {
	assert.equal(nextStatus('draft', 'approve'), 'approved');
	assert.equal(nextStatus('approved', 'request_changes'), 'changes_requested');
	assert.equal(nextStatus('changes_requested', 'comment'), 'changes_requested');
	assert.equal(nextStatus('draft', 'comment'), 'draft');
});

test('review input: reviewer required; requesting changes needs a comment', () => {
	assert.ok(reviewInput.safeParse({ version: 1, action: 'approve', reviewer: 'Minna' }).success);
	assert.ok(!reviewInput.safeParse({ version: 1, action: 'approve', reviewer: '  ' }).success);
	assert.ok(!reviewInput.safeParse({ version: 1, action: 'request_changes', reviewer: 'Minna', comment: '' }).success);
	assert.ok(reviewInput.safeParse({ version: 1, action: 'request_changes', reviewer: 'Minna', comment: 'Check peat parcels' }).success);
	assert.ok(!reviewInput.safeParse({ version: 0, action: 'approve', reviewer: 'Minna' }).success);
});

test('save input: needs a polygon, scenario and evidence ids', () => {
	const ok = {
		reportId: 'abc', name: 'Säkylä', geometry: { type: 'Polygon', coordinates: [[[22, 60.9], [22.6, 60.9], [22.6, 61.2], [22, 60.9]]] },
		scenario: { activePolicies: ['world_china'], year: 2050, risk: 'composite' }, summary: { farms: 108 }, evidenceIds: ['lens.parcels']
	};
	const parsed = saveReportInput.safeParse(ok);
	assert.ok(parsed.success);
	assert.equal(parsed.data.author, 'Climate Lens', 'default author');
	assert.ok(!saveReportInput.safeParse({ ...ok, geometry: { type: 'Point', coordinates: [22, 61] } }).success);
	assert.ok(!saveReportInput.safeParse({ ...ok, scenario: { ...ok.scenario, year: 1990 } }).success);
});
