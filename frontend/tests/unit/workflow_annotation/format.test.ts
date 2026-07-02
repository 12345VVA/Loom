import { describe, expect, it } from 'vitest';
import { pretty, parseJudgeDetail } from '/$/workflow_annotation/utils/format';

describe('workflow_annotation format utils', () => {
	// JSON 字段美化展示：抽屉中 inputData / actualOutput / expectedOutput 等都走此函数
	describe('pretty', () => {
		it('returns empty string for empty input', () => {
			expect(pretty(null)).toBe('');
			expect(pretty(undefined)).toBe('');
			expect(pretty('')).toBe('');
		});

		it('pretty-prints valid JSON string with 2-space indent', () => {
			const result = pretty('{"a":1,"b":2}');
			expect(result).toBe('{\n  "a": 1,\n  "b": 2\n}');
		});

		it('pretty-prints object directly with 2-space indent', () => {
			const result = pretty({ a: 1, b: 2 });
			expect(result).toBe('{\n  "a": 1,\n  "b": 2\n}');
		});

		it('returns raw string when parsed result is a string', () => {
			// JSON 字符串解析后仍是字符串：直接返回该字符串，避免多余引号
			expect(pretty('"hello"')).toBe('hello');
		});

		it('falls back to String(s) for invalid JSON string', () => {
			expect(pretty('not json')).toBe('not json');
			expect(pretty('{broken')).toBe('{broken');
		});

		it('handles nested objects', () => {
			const result = pretty({ outer: { inner: 1 } });
			expect(result).toContain('"outer":');
			expect(result).toContain('"inner": 1');
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
