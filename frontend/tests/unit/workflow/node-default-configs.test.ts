import { describe, expect, it } from 'vitest';
import { buildDefaultConfig, NODE_DEFAULT_CONFIGS } from '/$/workflow/utils/node-default-configs';

// 测试用 uniqueVar：直接拼接，便于断言
const uniqueVar = (label: string, d: string) => `${label}_${d}`;

describe('buildDefaultConfig', () => {
	it('llm：含静态字段 + 注入 outputVariable', () => {
		const cfg = buildDefaultConfig('llm', 'LLM', uniqueVar);
		expect(cfg.modelProfileCode).toBe('');
		expect(cfg.outputFormat).toBe('text');
		expect(cfg.jsonFields).toEqual([]);
		expect(cfg.outputVariable).toBe('LLM_output');
	});

	it('condition：无 outputVariable', () => {
		const cfg = buildDefaultConfig('condition', '条件', uniqueVar);
		expect(cfg.expression).toBe('');
		expect(cfg.trueRoute).toBe('');
		expect(cfg.outputVariable).toBeUndefined();
	});

	it('variable_transform：注入到 output_variable（snake_case）', () => {
		const cfg = buildDefaultConfig('variable_transform', '转换', uniqueVar);
		expect(cfg.output_variable).toBe('转换_transformed_value');
		expect(cfg.transform_type).toBe('join_array');
		expect(cfg.outputVariable).toBeUndefined();
	});

	it('end：静态默认', () => {
		const cfg = buildDefaultConfig('end', '结束', uniqueVar);
		expect(cfg.outputFormat).toBe('json');
		expect(cfg.outputFields).toEqual([]);
	});

	it('未知类型：返回空对象（不报错）', () => {
		const cfg = buildDefaultConfig('unknown_type', 'X', uniqueVar);
		expect(cfg).toEqual({});
	});

	it('每次构建返回独立的数组字段（不共享引用）', () => {
		const c1 = buildDefaultConfig('switch', 'S', uniqueVar);
		const c2 = buildDefaultConfig('switch', 'S', uniqueVar);
		expect(c1.cases).not.toBe(c2.cases);
		c1.cases.push({ id: 'x' });
		expect(c2.cases).toHaveLength(0);
	});

	it('NODE_DEFAULT_CONFIGS 覆盖所有需要 outputVariable 的核心类型', () => {
		const withOutputVar = Object.entries(NODE_DEFAULT_CONFIGS)
			.filter(([, spec]) => spec.outputVarDefault)
			.map(([type]) => type);
		expect(withOutputVar).toEqual(
			expect.arrayContaining([
				'llm',
				'human_input',
				'loop_controller',
				'batch_processor',
				'image_generator',
				'tool_executor',
				'variable_transform'
			])
		);
	});
});
