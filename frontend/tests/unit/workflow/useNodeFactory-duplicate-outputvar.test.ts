import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import type { Ref } from 'vue';
import { useNodeFactory } from '/$/workflow/composables/useNodeFactory';
import { NODE_DEFAULT_CONFIGS } from '/$/workflow/utils/node-default-configs';

// i18n：本项目 key 即中文，直接返回 key
const t = (k: string) => k;
const noopSnapshot = () => {};

// 最小节点结构（仅 duplicateNode 用到的字段）；config 值类型从宽
interface TestNode {
	id: string;
	type: string;
	label: string;
	position: { x: number; y: number };
	data: { config: Record<string, unknown> };
}

const elementsWith = (node: TestNode): Ref<TestNode[]> => ref<TestNode[]>([node]);

/**
 * H2 守护：duplicateNode 的输出变量去重必须按节点类型的权威字段名回写。
 * 三期B7（WF-P2-9）起 variable_transform 权威键统一驼峰 outputVariable：
 * - 读取经 resolveOutputVar 双风格（存量 snake 配置仍可识别旧值并去重）
 * - 回写只写驼峰权威键；存量 snake 键原样保留（迁移是配置面板打开时的职责）
 * 回归背景：旧实现只认固定键，导致复制后既不去重、又可能写入界面不显示的「影子字段」。
 */
describe('useNodeFactory duplicateNode 输出变量回写（H2）', () => {
	it('权威键映射：llm 与 variable_transform 均为 outputVariable（驼峰统一）', () => {
		expect(NODE_DEFAULT_CONFIGS.llm.outputVarKey ?? 'outputVariable').toBe('outputVariable');
		expect(NODE_DEFAULT_CONFIGS.variable_transform.outputVarKey).toBe('outputVariable');
	});

	it('复制 llm 节点：回写到 outputVariable，且不产生 output_variable 影子字段', () => {
		const elements = elementsWith({
			id: 'src',
			type: 'llm',
			label: 'LLM 节点',
			position: { x: 0, y: 0 },
			data: { config: { outputVariable: 'LLM节点_output', outputFormat: 'text' } }
		});
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		expect(copy.data.config.outputVariable).toBeTruthy();
		expect(copy.data.config.outputVariable).not.toBe('LLM节点_output');
		expect('output_variable' in copy.data.config).toBe(false);
	});

	it('复制 variable_transform（驼峰配置）：去重回写 outputVariable', () => {
		const elements = elementsWith({
			id: 'src',
			type: 'variable_transform',
			label: '数据转换',
			position: { x: 0, y: 0 },
			data: {
				config: { outputVariable: '数据转换_transformed_value', transformType: 'join_array' }
			}
		});
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		expect(copy.data.config.outputVariable).toBeDefined();
		expect(copy.data.config.outputVariable).not.toBe('数据转换_transformed_value');
		// 不得把值写到下划线影子字段
		expect('output_variable' in copy.data.config).toBe(false);
	});

	it('复制存量 snake 配置的 variable_transform：读旧值去重、写驼峰权威键、snake 原样保留', () => {
		const elements = elementsWith({
			id: 'src',
			type: 'variable_transform',
			label: '数据转换',
			position: { x: 0, y: 0 },
			data: { config: { output_variable: '数据转换_transformed_value', transform_type: 'join_array' } }
		});
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		// 双风格读取旧值 → 去重后写入驼峰权威键（复制即迁移到权威形态）
		expect(copy.data.config.outputVariable).toBeDefined();
		expect(copy.data.config.outputVariable).not.toBe('数据转换_transformed_value');
		// snake 旧键不删除不改写（迁移是配置面板打开时的职责，复制不动用户存量数据）
		expect(copy.data.config.output_variable).toBe('数据转换_transformed_value');
	});

	it('双键并存：只改写驼峰权威键，snake 保持原样（与面板迁移优先级一致）', () => {
		const elements = elementsWith({
			id: 'src',
			type: 'variable_transform',
			label: '数据转换',
			position: { x: 0, y: 0 },
			// 历史/导入数据可能同时存在两键；驼峰为权威（面板迁移同样驼峰优先）
			data: { config: { outputVariable: 'camelVar', output_variable: '数据转换_transformed_value' } }
		});
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		duplicateNode('src');
		const copy = elements.value[1];
		// 权威键被去重改写；非权威键不被新值覆盖
		expect(copy.data.config.outputVariable).not.toBe('camelVar');
		expect(copy.data.config.output_variable).toBe('数据转换_transformed_value');
	});

	it('outputVariable 为空串：不写入、不崩溃', () => {
		const elements = elementsWith({
			id: 'src',
			type: 'llm',
			label: 'LLM 节点',
			position: { x: 0, y: 0 },
			data: { config: { outputVariable: '' } }
		});
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		expect(duplicateNode('src')).toBe(true);
		const copy = elements.value[1];
		expect(copy.data.config.outputVariable).toBe('');
		expect('output_variable' in copy.data.config).toBe(false);
	});

	it('变量名去重后不与已存在节点冲突', () => {
		const elements = elementsWith({
			id: 'a',
			type: 'variable_transform',
			label: '数据转换',
			position: { x: 0, y: 0 },
			data: { config: { outputVariable: '数据转换_transformed_value' } }
		});
		const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
		duplicateNode('a');
		const copy = elements.value[1];
		expect(copy.data.config.outputVariable).not.toBe('数据转换_transformed_value');
	});
});
