import { describe, expect, it } from 'vitest';
import { getEdgeLabel } from '/$/workflow/utils/edge-label';

describe('getEdgeLabel', () => {
	it('condition: true → True, false → False', () => {
		expect(getEdgeLabel('true', { type: 'condition' })).toBe('True');
		expect(getEdgeLabel('false', { type: 'condition' })).toBe('False');
	});

	it('switch: default → 默认', () => {
		expect(getEdgeLabel('default', { type: 'switch' })).toBe('默认');
	});

	it('switch: case_<id> 取 case.value', () => {
		const node = { type: 'switch', data: { config: { cases: [{ id: 'c1', value: '易' }] } } };
		expect(getEdgeLabel('case_c1', node)).toBe('易');
	});

	it('switch: case.value 为空时回落 Case', () => {
		const node = { type: 'switch', data: { config: { cases: [{ id: 'c1', value: '' }] } } };
		expect(getEdgeLabel('case_c1', node)).toBe('Case');
	});

	it('switch: case id 找不到时回落 Case', () => {
		const node = { type: 'switch', data: { config: { cases: [] } } };
		expect(getEdgeLabel('case_xxx', node)).toBe('Case');
	});

	it('intent_classifier: intent_<id> 取 intent.name', () => {
		const node = {
			type: 'intent_classifier',
			data: { config: { intents: [{ id: 'i1', name: '闲聊' }] } }
		};
		expect(getEdgeLabel('intent_i1', node)).toBe('闲聊');
	});

	it('intent_classifier: default → 默认', () => {
		expect(getEdgeLabel('default', { type: 'intent_classifier' })).toBe('默认');
	});

	it('普通节点（无分支）返回 undefined', () => {
		expect(getEdgeLabel(undefined, { type: 'llm' })).toBeUndefined();
	});

	it('srcNode 为空返回 undefined', () => {
		expect(getEdgeLabel('true', undefined)).toBeUndefined();
	});

	// 回归保护：旧下标格式（case_0）的兜底已删除，现按 id 查找失败时回落 'Case'
	it('旧下标格式 case_0 不再走数字兜底（按 id 查找失败 → Case）', () => {
		const node = { type: 'switch', data: { config: { cases: [{ id: 'c1', value: '易' }] } } };
		expect(getEdgeLabel('case_0', node)).toBe('Case');
	});
});
