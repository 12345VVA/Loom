import { describe, expect, it } from 'vitest';
import {
	verdictType,
	statusTagType,
	caseStatusType,
	kappaLevelType,
	parseJudgeDetail
} from '/$/workflow_eval/utils/format';

describe('workflow_eval format utils', () => {
	// 锁住 verdict → element-plus tag type 映射，避免回归对比页颜色错配
	describe('verdictType', () => {
		it('maps known verdicts to correct tag types', () => {
			expect(verdictType('regression')).toBe('error');
			expect(verdictType('improvement')).toBe('success');
			expect(verdictType('insignificant')).toBe('info');
			expect(verdictType('insufficient_sample')).toBe('warning');
		});

		it('falls back to info for unknown verdict', () => {
			expect(verdictType('unknown')).toBe('info');
			expect(verdictType('')).toBe('info');
		});
	});

	// 锁住评估运行状态 → tag type 映射，运行列表/详情页强依赖颜色一致性
	describe('statusTagType', () => {
		it('maps known run statuses to correct tag types', () => {
			expect(statusTagType('succeeded')).toBe('success');
			expect(statusTagType('failed')).toBe('danger');
			expect(statusTagType('running')).toBe('warning');
			expect(statusTagType('cancelled')).toBe('info');
			expect(statusTagType('partial')).toBe('warning');
			expect(statusTagType('pending')).toBe('info');
		});

		it('falls back to empty string for unknown status', () => {
			expect(statusTagType('unknown')).toBe('');
			expect(statusTagType('')).toBe('');
		});
	});

	// 锁住用例执行状态 → tag type 映射（fail 与 error 都收敛到 danger）
	describe('caseStatusType', () => {
		it('maps known case statuses to correct tag types', () => {
			expect(caseStatusType('success')).toBe('success');
			expect(caseStatusType('fail')).toBe('danger');
			expect(caseStatusType('error')).toBe('danger');
			expect(caseStatusType('timeout')).toBe('warning');
			expect(caseStatusType('blocked')).toBe('info');
		});

		it('falls back to empty string for unknown status', () => {
			expect(caseStatusType('unknown')).toBe('');
			expect(caseStatusType('')).toBe('');
		});
	});

	// 锁住 κ 水平 → tag type 映射（judge 校准结果展示强依赖）
	describe('kappaLevelType', () => {
		it('maps known kappa levels to correct tag types', () => {
			expect(kappaLevelType('reliable')).toBe('success');
			expect(kappaLevelType('moderate')).toBe('warning');
			expect(kappaLevelType('unreliable')).toBe('danger');
			expect(kappaLevelType('no_annotation')).toBe('info');
		});

		it('falls back to info for unknown level', () => {
			expect(kappaLevelType('unknown')).toBe('info');
			expect(kappaLevelType('')).toBe('info');
		});
	});

	// 解析 evaluator_detail 字段：兼容 string/object，非法值兜底 null
	describe('parseJudgeDetail', () => {
		it('returns null for empty input', () => {
			expect(parseJudgeDetail(null)).toBeNull();
			expect(parseJudgeDetail(undefined)).toBeNull();
			expect(parseJudgeDetail('')).toBeNull();
			expect(parseJudgeDetail(0)).toBeNull();
		});

		it('returns object as-is without parsing', () => {
			const obj = { reason: 'ok', dimensions: [{ name: 'a', score: 1 }] };
			expect(parseJudgeDetail(obj)).toBe(obj);
		});

		it('parses valid JSON string', () => {
			const result = parseJudgeDetail('{"reason":"ok","score":0.8}');
			expect(result).toEqual({ reason: 'ok', score: 0.8 });
		});

		it('returns null for invalid JSON string without throwing', () => {
			expect(parseJudgeDetail('{not json')).toBeNull();
			expect(parseJudgeDetail('undefined')).toBeNull();
		});
	});
});
