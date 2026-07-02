import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useUpstreamVariables } from '/$/workflow/composables/useUpstreamVariables';

describe('useUpstreamVariables', () => {
	describe('getUpstreamVariablesForNode', () => {
		it('收集 start 节点的输入变量', () => {
			const elements = ref<any[]>([
				{
					id: 'start',
					type: 'start',
					label: '开始',
					data: { config: { inputVariables: ['query', 'topic'] } }
				},
				{ id: 'end', type: 'end', label: '结束', data: { config: {} } },
				{ id: 'e1', source: 'start', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			expect(vars.map(v => v.variableName)).toEqual(['query', 'topic']);
		});

		it('收集上游节点的 outputVariable', () => {
			const elements = ref<any[]>([
				{ id: 'start', type: 'start', label: '开始', data: { config: { inputVariables: [] } } },
				{ id: 'llm', type: 'llm', label: 'LLM', data: { config: { outputVariable: 'answer' } } },
				{ id: 'end', type: 'end', label: '结束', data: { config: {} } },
				{ id: 'e1', source: 'start', target: 'llm' },
				{ id: 'e2', source: 'llm', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			expect(vars.map(v => v.variableName)).toContain('answer');
		});

		it('llm 输出 json 时附带 jsonFields', () => {
			const elements = ref<any[]>([
				{
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
				},
				{ id: 'end', type: 'end', label: '结束', data: { config: {} } },
				{ id: 'e1', source: 'llm', target: 'end' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('end');
			const llmVar = vars.find(v => v.variableName === 'ans');
			expect(llmVar?.jsonFields).toEqual([{ name: 'a' }]);
		});

		it('循环上下文：注入 controller 的 itemVariable 并置于首位', () => {
			const elements = ref<any[]>([
				{
					id: 'lc',
					type: 'loop_controller',
					label: '循环',
					data: { config: { itemVariable: 'item' } }
				},
				{
					id: 'grp',
					type: 'loop_body_group',
					label: '循环体',
					data: { config: { controllerNodeId: 'lc' } }
				},
				{
					id: 'inner',
					type: 'llm',
					label: '内',
					parentNode: 'grp',
					data: { config: { outputVariable: 'inner_out' } }
				},
				{ id: 'e1', source: 'lc', target: 'inner' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			const vars = getUpstreamVariablesForNode('inner');
			expect(vars[0]).toMatchObject({ variableName: 'item', _isLoopContext: true });
		});

		it('去环：环路不会无限递归', () => {
			const elements = ref<any[]>([
				{ id: 'a', type: 'llm', label: 'A', data: { config: { outputVariable: 'va' } } },
				{ id: 'b', type: 'llm', label: 'B', data: { config: { outputVariable: 'vb' } } },
				{ id: 'e1', source: 'a', target: 'b' },
				{ id: 'e2', source: 'b', target: 'a' }
			]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			expect(() => getUpstreamVariablesForNode('b')).not.toThrow();
		});

		it('目标节点不存在时返回空数组', () => {
			const elements = ref<any[]>([]);
			const { getUpstreamVariablesForNode } = useUpstreamVariables(elements);
			expect(getUpstreamVariablesForNode('missing')).toEqual([]);
		});
	});

	describe('upstreamVariablesOf 缓存', () => {
		it('缓存命中：未失效前修改 elements 仍返回旧快照', () => {
			const elements = ref<any[]>([
				{
					id: 'start',
					type: 'start',
					label: '开始',
					data: { config: { inputVariables: ['q1'] } }
				},
				{ id: 'end', type: 'end', label: '结束', data: { config: {} } },
				{ id: 'e1', source: 'start', target: 'end' }
			]);
			const { upstreamVariablesOf } = useUpstreamVariables(elements);
			expect(upstreamVariablesOf('end').map(v => v.variableName)).toEqual(['q1']);
			// 加新输入变量但未失效缓存
			elements.value[0].data.config.inputVariables.push('q2');
			expect(upstreamVariablesOf('end').map(v => v.variableName)).toEqual(['q1']);
		});

		it('invalidateUpstreamCache 后重新计算', () => {
			const elements = ref<any[]>([
				{
					id: 'start',
					type: 'start',
					label: '开始',
					data: { config: { inputVariables: ['q1'] } }
				},
				{ id: 'end', type: 'end', label: '结束', data: { config: {} } },
				{ id: 'e1', source: 'start', target: 'end' }
			]);
			const { upstreamVariablesOf, invalidateUpstreamCache } = useUpstreamVariables(elements);
			upstreamVariablesOf('end');
			elements.value[0].data.config.inputVariables.push('q2');
			invalidateUpstreamCache();
			expect(upstreamVariablesOf('end').map(v => v.variableName)).toEqual(['q1', 'q2']);
		});

		it('nodeId 为空时返回 []', () => {
			const elements = ref<any[]>([]);
			const { upstreamVariablesOf } = useUpstreamVariables(elements);
			expect(upstreamVariablesOf(null)).toEqual([]);
			expect(upstreamVariablesOf(undefined)).toEqual([]);
		});
	});
});
