import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useNodeFactory } from '/$/workflow/composables/useNodeFactory';
import { NODE_DEFAULT_CONFIGS } from '/$/workflow/utils/node-default-configs';

// i18n：本项目 key 即中文，直接返回 key
const t = (k: string) => k;
const noopSnapshot = () => {};

/**
 * H2 守护：duplicateNode 的输出变量去重必须按节点类型的权威字段名回写。
 * - llm 类节点：权威键 `outputVariable`
 * - variable_transform：权威键 `output_variable`
 * 回归背景：旧实现只认 `outputVariable`，导致「数据转换」节点复制后
 * 既不去重、又可能写入界面不显示的「影子字段」。
 */
describe('useNodeFactory duplicateNode 输出变量回写（H2）', () => {
	it('权威键映射：llm→outputVariable，variable_transform→output_variable', () => {
		expect(NODE_DEFAULT_CONFIGS.llm.outputVarKey ?? 'outputVariable').toBe('outputVariable');
		expect(NODE_DEFAULT_CONFIGS.variable_transform.outputVarKey).toBe('output_variable');
	});

	it('复制 llm 节点：回写到 outputVariable，且不产生 output_variable 影子字段', () => {
		const elements = ref<any[]>([
			{
				id: 'src',
				type: 'llm',
				label: 'LLM 节点',
				position: { x: 0, y: 0 },
				data: { config: { outputVariable: 'LLM节点_output', outputFormat: 'text' } }
			}
		]);
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		expect(copy.data.config.outputVariable).toBeTruthy();
		expect(copy.data.config.outputVariable).not.toBe('LLM节点_output');
		expect('output_variable' in copy.data.config).toBe(false);
	});

	it('复制 variable_transform：回写到 output_variable（非 outputVariable）', () => {
		const elements = ref<any[]>([
			{
				id: 'src',
				type: 'variable_transform',
				label: '数据转换',
				position: { x: 0, y: 0 },
				data: { config: { output_variable: '数据转换_transformed_value', transform_type: 'join_array' } }
			}
		]);
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		// 权威键发生变化并被去重（旧实现完全不处理该类型）
		expect(copy.data.config.output_variable).toBeDefined();
		expect(copy.data.config.output_variable).not.toBe('数据转换_transformed_value');
		// 不得把值写到驼峰影子字段
		expect(copy.data.config.outputVariable).toBeUndefined();
	});

	it('variable_transform 两字段并存：只回写权威键，另一字段保持原样', () => {
		const elements = ref<any[]>([
			{
				id: 'src',
				type: 'variable_transform',
				label: '数据转换',
				position: { x: 0, y: 0 },
				// 历史/导入数据可能同时存在两键
				data: { config: { outputVariable: 'legacyCamel', output_variable: '数据转换_transformed_value' } }
			}
		]);
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		duplicateNode('src');
		const copy = elements.value[1];
		// 权威键被改写；非权威键不被新值覆盖
		expect(copy.data.config.output_variable).not.toBe('数据转换_transformed_value');
		expect(copy.data.config.outputVariable).toBe('legacyCamel');
	});

	it('outputVariable 为空串：不写入、不崩溃', () => {
		const elements = ref<any[]>([
			{
				id: 'src',
				type: 'llm',
				label: 'LLM 节点',
				position: { x: 0, y: 0 },
				data: { config: { outputVariable: '' } }
			}
		]);
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		expect(copy.data.config.outputVariable).toBe('');
		expect('output_variable' in copy.data.config).toBe(false);
	});

	it('变量名去重后不与已存在节点冲突', () => {
		const elements = ref<any[]>([
			{
				id: 'a',
				type: 'variable_transform',
				label: '数据转换',
				position: { x: 0, y: 0 },
				data: { config: { output_variable: '数据转换_transformed_value' } }
			}
		]);
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		duplicateNode('a');
		const copy = elements.value[1];
		expect(copy.data.config.output_variable).not.toBe('数据转换_transformed_value');
	});
});
