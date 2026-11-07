/**
 * Saved reports and the expert review log (stored in MongoDB Atlas).
 *
 * A report is identified by `reportId` (the drawn area's id) and saved as numbered versions;
 * every version is an immutable snapshot of the area facts, the scenario and the evidence used.
 * Reviews are appended to a log, never edited, so the audit trail shows who decided what, when.
 */
import { z } from 'zod';
import type { LensReport } from '../lens/types.ts';

export type ReportStatus = 'draft' | 'approved' | 'changes_requested';
export type ReviewAction = 'approve' | 'request_changes' | 'comment';

const position = z.tuple([z.number(), z.number()]);
export const saveReportInput = z.object({
	reportId: z.string().min(1).max(100),
	name: z.string().min(1).max(200),
	author: z.string().min(1).max(100).default('Climate Lens'),
	geometry: z.object({ type: z.literal('Polygon'), coordinates: z.array(z.array(position)).min(1) }),
	scenario: z.object({
		activePolicies: z.array(z.string().max(60)).max(50),
		year: z.number().int().min(2025).max(2100),
		risk: z.string().max(40)
	}),
	summary: z.record(z.string(), z.unknown()),
	evidenceIds: z.array(z.string().max(80)).max(100)
});
export type SaveReportInput = z.infer<typeof saveReportInput>;

export const reviewInput = z.object({
	version: z.number().int().min(1),
	action: z.enum(['approve', 'request_changes', 'comment']),
	reviewer: z.string().trim().min(1, 'Reviewer name is required').max(100),
	comment: z.string().trim().max(2000).default('')
}).refine((r) => r.action !== 'request_changes' || r.comment.length > 0, {
	message: 'Say what needs to change',
	path: ['comment']
});
export type ReviewInput = z.infer<typeof reviewInput>;

export interface ReportVersion extends Omit<SaveReportInput, 'reportId'> {
	reportId: string;
	version: number;
	status: ReportStatus;
	createdAt: string;
}
export interface Review extends ReviewInput {
	reportId: string;
	at: string;
}

/** Status after a review. Comments leave the status as it is. */
export function nextStatus(current: ReportStatus, action: ReviewAction): ReportStatus {
	if (action === 'approve') return 'approved';
	if (action === 'request_changes') return 'changes_requested';
	return current;
}

/** Compact, citable snapshot of a Climate Lens report for storage. */
export function reportSummary(r: LensReport) {
	return {
		packageVersion: r.package.version,
		reportYear: r.package.reportYear,
		farms: r.area.farms,
		parcels: r.area.parcels,
		hectares: r.area.hectares.value,
		contractHectares: r.area.contractHectares.value,
		topCrops: Object.entries(r.area.cropHa).slice(0, 5),
		peatContractCo2e: r.peat.contractCo2e.value,
		organicContractHa: r.peat.organicContractHa.value,
		soilMisreportCandidates: r.peat.misreportCandidates.map((m) => m.farm),
		catchments: r.catchments.map((c) => ({ id: c.id, status: c.status })),
		peaHeatBaseline: r.climate?.baseline.pHeatSeason ?? null,
		actions: r.actions.map((a) => ({ id: a.id, potential: a.potential?.value ?? null }))
	};
}
