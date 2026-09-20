import { describe, expect, it } from 'vitest';
import {
	detectProviderKind,
	parseProfileLimits,
	parseProfileSizeOptions
} from '/$/ai/utils/image-providers';

describe('detectProviderKind', () => {
	it('detects by adapter field', () => {
		expect(detectProviderKind({ providerAdapter: 'bailian' })).toBe('bailian');
		expect(detectProviderKind({ providerAdapter: 'volcengine-ark' })).toBe('volcengine-ark');
		expect(detectProviderKind({ providerAdapter: 'openai-compatible' })).toBe('openai');
		expect(detectProviderKind({ providerAdapter: 'qianfan' })).toBe('qianfan');
		expect(detectProviderKind({ providerAdapter: 'gemini' })).toBe('gemini');
	});

	it('detects by provider code / model code', () => {
		// providerCode 为严格相等匹配
		expect(detectProviderKind({ providerCode: 'bailian' })).toBe('bailian');
		expect(detectProviderKind({ modelCode: 'wan2.6-t2i' })).toBe('bailian');
		expect(detectProviderKind({ modelCode: 'doubao-seedream-4-0' })).toBe('volcengine-ark');
		expect(detectProviderKind({ providerCode: 'openai' })).toBe('openai');
		expect(detectProviderKind({ modelCode: 'ernie-irag-1.0' })).toBe('qianfan');
		expect(detectProviderKind({ providerCode: 'google-gemini' })).toBe('gemini');
	});

	it('falls back to provider name / model name heuristics', () => {
		expect(detectProviderKind({ providerName: '阿里百炼' })).toBe('bailian');
		expect(detectProviderKind({ providerName: '火山方舟' })).toBe('volcengine-ark');
		expect(detectProviderKind({ providerName: '百度千帆' })).toBe('qianfan');
		expect(detectProviderKind({ providerName: '谷歌 Gemini' })).toBe('gemini');
	});

	it('returns unknown for empty profile', () => {
		expect(detectProviderKind(undefined)).toBe('unknown');
		expect(detectProviderKind({})).toBe('unknown');
	});
});

describe('parseProfileSizeOptions / parseProfileLimits', () => {
	it('parses _sizes array from modelDefaultConfig', () => {
		const config = JSON.stringify({ _sizes: [{ label: '1:1', value: '1024x1024' }] });
		expect(parseProfileSizeOptions(config)).toEqual([{ label: '1:1', value: '1024x1024' }]);
	});

	it('returns null when _sizes missing or config invalid', () => {
		expect(parseProfileSizeOptions(undefined)).toBeNull();
		expect(parseProfileSizeOptions('{}')).toBeNull();
		expect(parseProfileSizeOptions('{bad json')).toBeNull();
	});

	it('parses _limits with defaults', () => {
		expect(parseProfileLimits(JSON.stringify({ _limits: { max_n: 4 } }))).toEqual({
			max_n: 4,
			max_prompt_length: undefined
		});
		expect(parseProfileLimits(undefined)).toEqual({ max_n: 8 });
		expect(parseProfileLimits('{bad json')).toEqual({ max_n: 8 });
	});
});
