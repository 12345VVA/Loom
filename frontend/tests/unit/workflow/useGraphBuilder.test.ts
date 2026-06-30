import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useGraphBuilder } from '/$/workflow/composables/useGraphBuilder';

describe('useGraphBuilder', () => {
	describe('persistSignature', () => {
		it('strips runtime-only fields (class, data.runLog, data.runData) but keeps config', () => {
			const { persistSignature } = useGraphBuilder(ref<any[]>([]));
			const sig = persistSignature([
				{ id: 'n1', class: 'running', data: { config: { a: 1 }, runLog: 'x', runData: 'y' } }
			]);
			const parsed = JSON.parse(sig);
			expect(parsed[0].class).toBeUndefined();
			expect(parsed[0].data.runLog).toBeUndefined();
			expect(parsed[0].data.runData).toBeUndefined();
			expect(parsed[0].data.config).toEqual({ a: 1 });
		});

		it('passes falsy entries through unchanged', () => {
			const { persistSignature } = useGraphBuilder(ref<any[]>([]));
			const parsed = JSON.parse(persistSignature([null, { id: 'n1', data: { config: 1 } }]));
			expect(parsed[0]).toBeNull();
			expect(parsed[1].data.config).toBe(1);
		});
	});

	describe('buildGraphPayload', () => {
		function makeElements() {
			return ref<any[]>([
				{
					id: 'start-1',
					type: 'start',
					label: '开始',
					position: { x: 0, y: 0 },
					data: { config: {}, runLog: 'should-be-stripped' }
				},
				{
					id: 'tool-1',
					type: 'tool_executor',
					label: '工具',
					position: { x: 100, y: 0 },
					data: { config: { argumentsJson: '{"q":"a"}', tool: 'foo' } }
				},
				{
					id: 'e1',
					source: 'start-1',
					target: 'tool-1',
					type: 'direct',
					sourceHandle: 'out',
					data: { condition: '', label: 'L' }
				}
			]);
		}

		// [P0 回归] tool_executor 的 argumentsJson 应解析为 arguments 对象，
		// 且 nodes[].config 不再残留 argumentsJson 字符串字段
		it('parses tool_executor.argumentsJson into arguments object and drops the string field', () => {
			const { buildGraphPayload } = useGraphBuilder(makeElements());
			const toolNode = buildGraphPayload().nodes.find(n => n.type === 'tool_executor');
			expect(toolNode.config.arguments).toEqual({ q: 'a' });
			expect(toolNode.config.argumentsJson).toBeUndefined();
		});

		it('keeps argumentsJson in cleanElements for canvas restore', () => {
			const { buildGraphPayload } = useGraphBuilder(makeElements());
			const toolEl = buildGraphPayload().elements.find(el => el.id === 'tool-1');
			expect(toolEl.data.config.argumentsJson).toBe('{"q":"a"}');
		});

		it('strips runLog from cleanElements to avoid bloat', () => {
			const { buildGraphPayload } = useGraphBuilder(makeElements());
			const startEl = buildGraphPayload().elements.find(el => el.id === 'start-1');
			expect(startEl.data.runLog).toBeUndefined();
		});

		it('serializes edges with sourceHandle and label', () => {
			const { buildGraphPayload } = useGraphBuilder(makeElements());
			const edges = buildGraphPayload().edges;
			expect(edges).toHaveLength(1);
			expect(edges[0].sourceHandle).toBe('out');
			expect(edges[0].data).toEqual({ label: 'L' });
			expect(edges[0].condition).toBe('');
		});

		it('serializes parentNode/extent/expandParent when present', () => {
			const { buildGraphPayload } = useGraphBuilder(
				ref<any[]>([
					{
						id: 'child',
						type: 'llm',
						label: 'c',
						position: { x: 1, y: 1 },
						data: { config: {} },
						parentNode: 'grp',
						extent: 'parent',
						expandParent: true
					}
				])
			);
			const node = buildGraphPayload().nodes[0];
			expect(node.parentNode).toBe('grp');
			expect(node.extent).toBe('parent');
			expect(node.expandParent).toBe(true);
		});
	});
});
