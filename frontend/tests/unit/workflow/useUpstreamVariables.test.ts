import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useUpstreamVariables } from '/$/workflow/composables/useUpstreamVariables';
import type { FlowEdge, FlowNode } from '/$/workflow/types/editor';

/** fixture 工厂：补齐 FlowNode 必填的 position/label（断言只看返回的 vars，默认值不参与比较） */
function makeNode(overrides: Partial<FlowNode> & Pick<FlowNode, 'id' | 'type'>): FlowNode {
	return { label: '', position: { x: 0, y: 0 }, data: { config: {} }, ...overrides };
}

describe('useUpstreamVariables', () => {
	describe('getUpstreamVariablesForNode', () => {
		it('收集 start 节点的输入变量', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({
					id: 'start',
					type: 'start',
					label: '开始',
					data: { config: { inputVariables: ['query', 'topic'] } }
				}),
				makeNode({ id: 'end', type: 'end', label: '结束' }),
				{ id: 'e1', source: 'start', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			expect(vars.map(v => v.variableName)).toEqual(['query', 'topic']);
		});

		it('WFI-1b：start 声明的 type 透传为 variableType，生图输出标 image', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({
					id: 'start',
					type: 'start',
					label: '开始',
					data: {
						config: {
							inputVariables: [
								{ name: 'input_image', type: 'image' },
								{ name: 'query' }
							]
						}
					}
				}),
				makeNode({
					id: 'gen',
					type: 'image_generator',
					label: '生图',
					data: { config: { outputVariable: 'cover' } }
				}),
				makeNode({ id: 'llm', type: 'llm', label: 'LLM', data: { config: { outputVariable: 'ans' } } }),
				makeNode({ id: 'end', type: 'end', label: '结束' }),
				{ id: 'e1', source: 'start', target: 'gen' },
				{ id: 'e2', source: 'gen', target: 'llm' },
				{ id: 'e3', source: 'llm', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			const byName = Object.fromEntries(vars.map(v => [v.variableName, v]));
			expect(byName.input_image.variableType).toBe('image');
			expect(byName.query.variableType).toBe('string');
			expect(byName.cover.variableType).toBe('image');
			expect(byName.ans.variableType).toBeUndefined();
		});

		it('收集上游节点的 outputVariable', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({ id: 'start', type: 'start', label: '开始', data: { config: { inputVariables: [] } } }),
				makeNode({ id: 'llm', type: 'llm', label: 'LLM', data: { config: { outputVariable: 'answer' } } }),
				makeNode({ id: 'end', type: 'end', label: '结束' }),
				{ id: 'e1', source: 'start', target: 'llm' },
				{ id: 'e2', source: 'llm', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			expect(vars.map(v => v.variableName)).toContain('answer');
		});

		it('llm 输出 json 时附带 jsonFields', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({
					id: 'llm',
					type: 'llm',
					label: 'LLM',
					data: {
						config: {
							outputVariable: 'ans',
							outputFormat: 'json',
							jsonFields: [{ name: 'a' }]
						}
					}
				}),
				makeNode({ id: 'end', type: 'end', label: '结束' }),
				{ id: 'e1', source: 'llm', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			const llmVar = vars.find(v => v.variableName === 'ans');
			expect(llmVar?.jsonFields).toEqual([{ name: 'a' }]);
		});

		it('循环上下文：注入 controller 的 itemVariable 并置于首位', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({
					id: 'lc',
					type: 'loop_controller',
					label: '循环',
					data: { config: { itemVariable: 'item' } }
				}),
				makeNode({
					id: 'grp',
					type: 'loop_body_group',
					label: '循环体',
					data: { config: { controllerNodeId: 'lc' } }
				}),
				makeNode({
					id: 'inner',
					type: 'llm',
					label: '内',
					parentNode: 'grp',
					data: { config: { outputVariable: 'inner_out' } }
				}),
				{ id: 'e1', source: 'lc', target: 'inner' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('inner');
			expect(vars[0]).toMatchObject({ variableName: 'item', _isLoopContext: true });
		});

		it('去环：环路不会无限递归', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({ id: 'a', type: 'llm', label: 'A', data: { config: { outputVariable: 'va' } } }),
				makeNode({ id: 'b', type: 'llm', label: 'B', data: { config: { outputVariable: 'vb' } } }),
				{ id: 'e1', source: 'a', target: 'b' },
				{ id: 'e2', source: 'b', target: 'a' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			expect(() => getUpstreamVariablesForNode('b')).not.toThrow();
		});

		it('目标节点不存在时返回空数组', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			expect(getUpstreamVariablesForNode('missing')).toEqual([]);
		});
	});

	describe('upstreamVariablesOf 缓存', () => {
		it('缓存命中：未失效前修改 elements 仍返回旧快照', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({
					id: 'start',
					type: 'start',
					label: '开始',
					data: { config: { inputVariables: ['q1'] } }
				}),
				makeNode({ id: 'end', type: 'end', label: '结束' }),
				{ id: 'e1', source: 'start', target: 'end' }
			]);
			const { upstreamVariablesOf } = useUpstreamVariables(elements);
			expect(upstreamVariablesOf('end').map(v => v.variableName)).toEqual(['q1']);
			// 加新输入变量但未失效缓存
			(elements.value[0] as FlowNode).data.config.inputVariables.push('q2');
			expect(upstreamVariablesOf('end').map(v => v.variableName)).toEqual(['q1']);
		});

		it('invalidateUpstreamCache 后重新计算', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([
				makeNode({
					id: 'start',
					type: 'start',
					label: '开始',
					data: { config: { inputVariables: ['q1'] } }
				}),
				makeNode({ id: 'end', type: 'end', label: '结束' }),
				{ id: 'e1', source: 'start', target: 'end' }
			]);
			const { upstreamVariablesOf, invalidateUpstreamCache } = useUpstreamVariables(elements);
			upstreamVariablesOf('end');
			(elements.value[0] as FlowNode).data.config.inputVariables.push('q2');
			invalidateUpstreamCache();
			expect(upstreamVariablesOf('end').map(v => v.variableName)).toEqual(['q1', 'q2']);
		});

		it('nodeId 为空时返回 []', () => {
			const elements = ref<(FlowNode | FlowEdge)[]>([]);
			const { upstreamVariablesOf } = useUpstreamVariables(elements);
			expect(upstreamVariablesOf(null)).toEqual([]);
			expect(upstreamVariablesOf(undefined)).toEqual([]);
		});
	});
});
