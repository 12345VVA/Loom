import { describe, expect, it } from 'vitest';
import { getMissingConfigFields, isRequiredConfigMissing } from '/$/workflow/utils';

// 构造一个最小节点结构（仅测试用到的字段）
function node(type: string, config: Record<string, any> = {}) {
	return { type, data: { config } };
}

describe('workflow getMissingConfigFields', () => {
	it('returns [] for node types without required business fields', () => {
		expect(getMissingConfigFields(node('start'))).toEqual([]);
		expect(getMissingConfigFields(node('end'))).toEqual([]);
		expect(getMissingConfigFields(node('loop_controller'))).toEqual([]);
		// 防御：异常/空入参不抛错
		expect(getMissingConfigFields({ type: 'unknown' })).toEqual([]);
		expect(getMissingConfigFields({} as any)).toEqual([]);
	});

	it('lists every missing field for llm / image_generator', () => {
		expect(getMissingConfigFields(node('llm'))).toEqual(['AI 模型', '提示词模板']);
		expect(getMissingConfigFields(node('llm', { modelProfileCode: 'gpt' }))).toEqual([
			'提示词模板'
		]);
		expect(
			getMissingConfigFields(node('llm', { modelProfileCode: 'gpt', promptTemplate: 'hi' }))
		).toEqual([]);
		expect(getMissingConfigFields(node('image_generator'))).toEqual(['AI 模型', '提示词模板']);
	});

	it('detects single-field requirements', () => {
		expect(getMissingConfigFields(node('condition'))).toEqual(['条件表达式']);
		expect(getMissingConfigFields(node('condition', { expression: 'x>1' }))).toEqual([]);
		expect(getMissingConfigFields(node('tool_executor'))).toEqual(['工具']);
		expect(getMissingConfigFields(node('tool_executor', { toolCode: 't1' }))).toEqual([]);
		expect(getMissingConfigFields(node('human_input'))).toEqual(['提示消息']);
		expect(getMissingConfigFields(node('human_input', { message: 'hi' }))).toEqual([]);
		expect(getMissingConfigFields(node('variable_assignment'))).toEqual(['赋值规则']);
		expect(
			getMissingConfigFields(node('variable_assignment', { assignments: [{ a: 1 }] }))
		).toEqual([]);
	});

	it('lists both missing fields for switch', () => {
		expect(getMissingConfigFields(node('switch'))).toEqual(['判断变量', '分支配置']);
		expect(getMissingConfigFields(node('switch', { variable: 'x' }))).toEqual(['分支配置']);
		expect(getMissingConfigFields(node('switch', { variable: 'x', cases: [{ id: 'c1' }] }))).toEqual(
			[]
		);
	});

	it('lists three missing fields for variable_transform', () => {
		expect(getMissingConfigFields(node('variable_transform'))).toEqual([
			'输入变量',
			'转换类型',
			'输出变量'
		]);
		expect(
			getMissingConfigFields(
				node('variable_transform', {
					input_variable: 'a',
					transform_type: 'upper',
					output_variable: 'b'
				})
			)
		).toEqual([]);
	});

	it('lists missing fields for intent_classifier', () => {
		expect(getMissingConfigFields(node('intent_classifier'))).toEqual(['AI 模型', '意图分支']);
		expect(
			getMissingConfigFields(node('intent_classifier', { intents: [{ id: 'i1' }] }))
		).toEqual(['AI 模型']);
	});
});

describe('workflow isRequiredConfigMissing', () => {
	it('returns true iff getMissingConfigFields is non-empty', () => {
		expect(isRequiredConfigMissing(node('llm'))).toBe(true);
		expect(isRequiredConfigMissing(node('llm', { modelProfileCode: 'gpt', promptTemplate: 'p' }))).toBe(
			false
		);
		expect(isRequiredConfigMissing(node('start'))).toBe(false);
		// 与 getMissingConfigFields 保持一致
		expect(isRequiredConfigMissing(node('switch'))).toBe(
			getMissingConfigFields(node('switch')).length > 0
		);
	});
});
