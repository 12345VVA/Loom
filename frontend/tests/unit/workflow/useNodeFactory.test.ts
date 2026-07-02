import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useNodeFactory } from '/$/workflow/composables/useNodeFactory';
import { getNodeMeta } from '/$/workflow/utils/node-type-registry';

// i18n：本项目 key 即中文，直接返回 key
const t = (k: string) => k;
const noopSnapshot = () => {};

// 动态获取 llm 的本地化标签，避免硬编码 labelKey
const llmLabel = t(getNodeMeta('llm').labelKey || '');
// outputVariable 经 sanitizeLabel 去空白：'LLM 节点' → 'LLM节点'
const sanitizedLlmLabel = llmLabel.replace(/\s+/g, '');

describe('useNodeFactory', () => {
	describe('getNextLabel', () => {
		it('同类型不存在时返回基础名', () => {
			const elements = ref<any[]>([]);
			const { getNextLabel } = useNodeFactory(elements, t, noopSnapshot);
			expect(getNextLabel('llm')).toBe(llmLabel);
		});

		it('已有同类型节点时追加递增序号', () => {
			const elements = ref<any[]>([{ id: 'l1', type: 'llm', label: llmLabel, data: { config: {} } }]);
			const { getNextLabel } = useNodeFactory(elements, t, noopSnapshot);
			expect(getNextLabel('llm')).toBe(`${llmLabel} 2`);
		});

		it('序号取已有最大值 +1', () => {
			const elements = ref<any[]>([
				{ id: 'l1', type: 'llm', label: llmLabel, data: { config: {} } },
				{ id: 'l2', type: 'llm', label: `${llmLabel} 3`, data: { config: {} } }
			]);
			const { getNextLabel } = useNodeFactory(elements, t, noopSnapshot);
			expect(getNextLabel('llm')).toBe(`${llmLabel} 4`);
		});
	});

	describe('getUniqueOutputVar', () => {
		it('无冲突时返回 label 前缀 + 默认名', () => {
			const elements = ref<any[]>([]);
			const { getUniqueOutputVar } = useNodeFactory(elements, t, noopSnapshot);
			expect(getUniqueOutputVar('LLM', 'output')).toBe('LLM_output');
		});

		it('有冲突时追加 _2/_3 后缀', () => {
			const elements = ref<any[]>([
				{ id: 'l1', type: 'llm', data: { config: { outputVariable: 'LLM_output' } } }
			]);
			const { getUniqueOutputVar } = useNodeFactory(elements, t, noopSnapshot);
			expect(getUniqueOutputVar('LLM', 'output')).toBe('LLM_output_2');
		});

		it('清洗标签中的非法字符（仅留字母数字下划线中文）', () => {
			const elements = ref<any[]>([]);
			const { getUniqueOutputVar } = useNodeFactory(elements, t, noopSnapshot);
			// 空格与括号被剔除
			expect(getUniqueOutputVar('LLM (1)', 'output')).toBe('LLM1_output');
		});
	});

	describe('handleAddNode', () => {
		it('添加 llm 节点：config 含静态字段与去重的 outputVariable', () => {
			const elements = ref<any[]>([]);
			const { handleAddNode } = useNodeFactory(elements, t, noopSnapshot);
			handleAddNode('llm', 100, 100);
			expect(elements.value).toHaveLength(1);
			const node = elements.value[0];
			expect(node.type).toBe('llm');
			expect(node.label).toBe(llmLabel);
			expect(node.data.config.outputFormat).toBe('text');
			expect(node.data.config.outputVariable).toBe(`${sanitizedLlmLabel}_output`);
		});

		it('添加 loop_controller 时自动创建 loop_body_group', () => {
			const elements = ref<any[]>([]);
			const { handleAddNode } = useNodeFactory(elements, t, noopSnapshot);
			handleAddNode('loop_controller', 100, 100);
			expect(elements.value).toHaveLength(2);
			const group = elements.value.find(el => el.type === 'loop_body_group');
			expect(group).toBeDefined();
			expect(group.data.config.controllerNodeId).toBe(elements.value[0].id);
		});

		it('记录撤销快照', () => {
			const elements = ref<any[]>([]);
			let snapshotted = 0;
			const { handleAddNode } = useNodeFactory(elements, t, () => snapshotted++);
			handleAddNode('llm', 0, 0);
			expect(snapshotted).toBe(1);
		});

		it('落入 group 时设 parentNode 并转局部坐标', () => {
			const elements = ref<any[]>([
				{
					id: 'grp',
					type: 'loop_body_group',
					position: { x: 0, y: 0 },
					style: { width: '400px', height: '250px' },
					data: { config: {} }
				}
			]);
			const { handleAddNode } = useNodeFactory(elements, t, noopSnapshot);
			handleAddNode('llm', 100, 100); // 命中 grp（x+50=150 在 [0,400]）
			const node = elements.value.find(el => el.type === 'llm');
			expect(node.parentNode).toBe('grp');
			expect(node.expandParent).toBe(true);
			expect(node.position.x).toBe(100); // x - hit.x = 100 - 0
		});

		it('已有 start 时拒绝再添加 start（不 push、不记快照）', () => {
			const elements = ref<any[]>([{ id: 's1', type: 'start', data: { config: {} } }]);
			let snapped = 0;
			const { handleAddNode } = useNodeFactory(elements, t, () => snapped++);
			handleAddNode('start', 100, 100);
			expect(elements.value).toHaveLength(1);
			expect(snapped).toBe(0);
		});

		it('已有 end 时拒绝再添加 end（不 push、不记快照）', () => {
			const elements = ref<any[]>([{ id: 'e1', type: 'end', data: { config: {} } }]);
			let snapped = 0;
			const { handleAddNode } = useNodeFactory(elements, t, () => snapped++);
			handleAddNode('end', 100, 100);
			expect(elements.value).toHaveLength(1);
			expect(snapped).toBe(0);
		});
	});

	describe('duplicateNode', () => {
		it('成功复制 llm 节点：生成新 id/label、输出变量去重、记录快照', () => {
			const elements = ref<any[]>([
				{
					id: 'src',
					type: 'llm',
					label: llmLabel,
					position: { x: 100, y: 100 },
					data: { config: { outputVariable: 'out', modelProfileCode: 'p1' } }
				}
			]);
			let snapped = 0;
			const { duplicateNode } = useNodeFactory(elements, t, () => snapped++);
			const ok = duplicateNode('src');
			expect(ok).toBe(true);
			expect(elements.value).toHaveLength(2);
			const copy = elements.value[1];
			expect(copy.id).not.toBe('src');
			expect(copy.label).toBe(`${llmLabel} 2`);
			// 副本输出变量名经去重，不与源节点冲突
			expect(copy.data.config.outputVariable).not.toBe('out');
			expect(snapped).toBe(1);
		});

		it('复制 switch 节点时重分配 case 稳定 id', () => {
			const elements = ref<any[]>([
				{
					id: 'src',
					type: 'switch',
					label: 'Switch',
					position: { x: 0, y: 0 },
					data: { config: { cases: [{ id: 'case_a', value: 'x' }] } }
				}
			]);
			const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
			duplicateNode('src');
			const copy = elements.value[1];
			expect(copy.data.config.cases[0].id).not.toBe('case_a');
			expect(copy.data.config.cases[0].id).toBeTruthy();
		});

		it('拒绝复制 start / end 节点（返回 false、不 push）', () => {
			const elements = ref<any[]>([{ id: 's', type: 'start', data: { config: {} } }]);
			let snapped = 0;
			const { duplicateNode } = useNodeFactory(elements, t, () => snapped++);
			expect(duplicateNode('s')).toBe(false);
			expect(elements.value).toHaveLength(1);
			expect(snapped).toBe(0);
		});

		it('目标节点不存在时返回 false', () => {
			const elements = ref<any[]>([]);
			const { duplicateNode } = useNodeFactory(elements, t, noopSnapshot);
			expect(duplicateNode('nope')).toBe(false);
		});
	});
});
