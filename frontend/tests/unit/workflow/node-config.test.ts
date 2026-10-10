import { describe, expect, it } from 'vitest';
import { getMissingConfigFields, isRequiredConfigMissing } from '/$/workflow/utils';

// 构造一个最小节点结构（仅测试用到的字段）
function node(type: string, config: Record<string, any> = {}) {
	return { type, data: { config } };
}

/**
 * F3（UI/UX 审查 2026-10-10）起必填口径单一来源：getMissingConfigFields 从
 * node-manifest 的 configFields（后端 NODE_CONFIG_SCHEMA 导出）派生。
 * 本组测试锚定前端派生行为与后端权威的一致性——标签/顺序即 manifest 下发值。
 */
describe('workflow getMissingConfigFields', () => {
	it('returns [] for node types without required business fields', () => {
		expect(getMissingConfigFields(node('start'))).toEqual([]);
		expect(getMissingConfigFields(node('end'))).toEqual([]);
		expect(getMissingConfigFields(node('memory_recall'))).toEqual([]);
		// intent_classifier 无静态必填（modelProfileCode 是「intents 非空才必填」
		// 的条件语义，后端 step6 权威；空 intents 直落 default 合法）
		expect(getMissingConfigFields(node('intent_classifier'))).toEqual([]);
		// 防御：异常/空入参不抛错
		expect(getMissingConfigFields({ type: 'unknown' })).toEqual([]);
		expect(getMissingConfigFields({} as any)).toEqual([]);
	});

	it('lists every missing field for llm / image_generator（manifest label 与顺序）', () => {
		expect(getMissingConfigFields(node('llm'))).toEqual(['提示词模板', 'AI 模型']);
		expect(getMissingConfigFields(node('llm', { modelProfileCode: 'gpt' }))).toEqual([
			'提示词模板'
		]);
		expect(
			getMissingConfigFields(node('llm', { modelProfileCode: 'gpt', promptTemplate: 'hi' }))
		).toEqual([]);
		expect(getMissingConfigFields(node('image_generator'))).toEqual(['提示词模板', 'AI 模型']);
	});

	it('loop/batch 列表变量必填（F3 补齐前后端漂移的缺口）', () => {
		expect(getMissingConfigFields(node('loop_controller'))).toEqual(['循环列表变量']);
		expect(getMissingConfigFields(node('loop_controller', { listVariable: 'items' }))).toEqual(
			[]
		);
		expect(getMissingConfigFields(node('batch_processor'))).toEqual(['批处理列表变量']);
		expect(
			getMissingConfigFields(node('batch_processor', { batchListVariable: 'rows' }))
		).toEqual([]);
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
		expect(getMissingConfigFields(node('memory_store'))).toEqual(['记忆内容模板']);
		expect(getMissingConfigFields(node('memory_store', { contentTemplate: 'x' }))).toEqual([]);
	});

	it('lists both missing fields for switch（后端 label：分支变量/分支列表）', () => {
		expect(getMissingConfigFields(node('switch'))).toEqual(['分支变量', '分支列表']);
		expect(getMissingConfigFields(node('switch', { variable: 'x' }))).toEqual(['分支列表']);
		expect(getMissingConfigFields(node('switch', { variable: 'x', cases: [{ id: 'c1' }] }))).toEqual(
			[]
		);
	});

	it('variable_transform 仅输入变量/转换类型必填（outputVariable 有默认名不报）', () => {
		expect(getMissingConfigFields(node('variable_transform'))).toEqual(['输入变量', '转换类型']);
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

	it('variable_transform 驼峰配置同样视为完整（三期B7 权威键回归）', () => {
		// 回归背景：三期B7 写入侧统一驼峰后，此处曾只读 snake 键，
		// 导致新建/面板迁移后的节点被误报「三项必填全缺失」并阻断保存/测试
		expect(
			getMissingConfigFields(
				node('variable_transform', {
					inputVariable: 'a',
					transformType: 'upper',
					outputVariable: 'b'
				})
			)
		).toEqual([]);
		expect(
			isRequiredConfigMissing(
				node('variable_transform', { inputVariable: 'a', transformType: 'upper' })
			)
		).toBe(false);
		// 双键混布：任一侧有值即视为已配置
		expect(
			getMissingConfigFields(
				node('variable_transform', {
					inputVariable: 'a',
					transform_type: 'upper',
					outputVariable: 'b'
				})
			)
		).toEqual([]);
	});

	it('blank 判定对齐后端 _is_blank（空白串/空数组视为缺失）', () => {
		expect(getMissingConfigFields(node('condition', { expression: '   ' }))).toEqual([
			'条件表达式'
		]);
		expect(getMissingConfigFields(node('switch', { variable: 'x', cases: [] }))).toEqual([
			'分支列表'
		]);
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
