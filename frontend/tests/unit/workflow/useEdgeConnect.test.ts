import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useEdgeConnect } from '/$/workflow/composables/useEdgeConnect';

const t = (k: string) => k;
const noopSnapshot = () => {};

describe('useEdgeConnect', () => {
	it('合法连接：生成新边并记录快照', () => {
		const elements = ref<any[]>([
			{ id: 'a', type: 'llm', data: { config: {} } },
			{ id: 'b', type: 'llm', data: { config: {} } }
		]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		onConnect({ source: 'a', target: 'b', sourceHandle: null } as any);
		expect(
			elements.value.some(el => 'source' in el && el.source === 'a' && el.target === 'b')
		).toBe(true);
		expect(snapped).toBe(1);
	});

	it('去重：同 source+target+sourceHandle 不重复加边', () => {
		const elements = ref<any[]>([
			{ id: 'a', type: 'llm', data: { config: {} } },
			{ id: 'b', type: 'llm', data: { config: {} } },
			{ id: 'e1', source: 'a', target: 'b', sourceHandle: null }
		]);
		const { onConnect } = useEdgeConnect(elements, t, noopSnapshot);
		onConnect({ source: 'a', target: 'b', sourceHandle: null } as any);
		expect(elements.value.filter(el => 'source' in el)).toHaveLength(1);
	});

	it('condition 连线：写回 trueRoute 并生成 True 标签、animated=false', () => {
		const elements = ref<any[]>([
			{ id: 'c', type: 'condition', data: { config: {} } },
			{ id: 't', type: 'llm', data: { config: {} } }
		]);
		const { onConnect } = useEdgeConnect(elements, t, noopSnapshot);
		onConnect({ source: 'c', target: 't', sourceHandle: 'true' } as any);
		expect(elements.value[0].data.config.trueRoute).toBe('t');
		const edge = elements.value.find(el => 'source' in el);
		expect(edge.data.label).toBe('True');
		expect(edge.animated).toBe(false);
	});

	it('switch case 连线：标签取 case.value', () => {
		const elements = ref<any[]>([
			{
				id: 's',
				type: 'switch',
				data: { config: { cases: [{ id: 'c1', value: '易' }] } }
			},
			{ id: 't', type: 'llm', data: { config: {} } }
		]);
		const { onConnect } = useEdgeConnect(elements, t, noopSnapshot);
		onConnect({ source: 's', target: 't', sourceHandle: 'case_c1' } as any);
		const edge = elements.value.find(el => 'source' in el);
		expect(edge.data.label).toBe('易');
	});

	it('普通节点连线：无标签、animated=true', () => {
		const elements = ref<any[]>([
			{ id: 'a', type: 'llm', data: { config: {} } },
			{ id: 'b', type: 'llm', data: { config: {} } }
		]);
		const { onConnect } = useEdgeConnect(elements, t, noopSnapshot);
		onConnect({ source: 'a', target: 'b', sourceHandle: null } as any);
		const edge = elements.value.find(el => 'source' in el);
		expect(edge.data.label).toBeUndefined();
		expect(edge.animated).toBe(true);
	});

	it('拒绝自身连接', () => {
		const elements = ref<any[]>([{ id: 'a', type: 'llm', data: { config: {} } }]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		onConnect({ source: 'a', target: 'a', sourceHandle: null } as any);
		expect(elements.value.filter(el => 'source' in el)).toHaveLength(0);
		expect(snapped).toBe(0);
	});

	it('拒绝 end 节点出边', () => {
		const elements = ref<any[]>([
			{ id: 'e', type: 'end', data: { config: {} } },
			{ id: 'x', type: 'llm', data: { config: {} } }
		]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		onConnect({ source: 'e', target: 'x', sourceHandle: null } as any);
		expect(elements.value.filter(el => 'source' in el)).toHaveLength(0);
		expect(snapped).toBe(0);
	});

	it('拒绝 start 节点入边', () => {
		const elements = ref<any[]>([
			{ id: 's', type: 'start', data: { config: {} } },
			{ id: 'x', type: 'llm', data: { config: {} } }
		]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		onConnect({ source: 'x', target: 's', sourceHandle: null } as any);
		expect(elements.value.filter(el => 'source' in el)).toHaveLength(0);
		expect(snapped).toBe(0);
	});

	it('condition 同分支已连线时拒绝重复', () => {
		const elements = ref<any[]>([
			{ id: 'c', type: 'condition', data: { config: {} } },
			{ id: 't1', type: 'llm', data: { config: {} } },
			{ id: 't2', type: 'llm', data: { config: {} } },
			{ id: 'e1', source: 'c', target: 't1', sourceHandle: 'true' }
		]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		// true 分支已连 t1，再连 t2 应拒绝
		onConnect({ source: 'c', target: 't2', sourceHandle: 'true' } as any);
		const edges = elements.value.filter(el => 'source' in el);
		expect(edges).toHaveLength(1);
		expect(edges[0].target).toBe('t1');
		expect(snapped).toBe(0);
	});

	it('switch 同端口已连线时拒绝重复', () => {
		const elements = ref<any[]>([
			{ id: 's', type: 'switch', data: { config: { cases: [{ id: 'c1', value: 'a' }] } } },
			{ id: 't1', type: 'llm', data: { config: {} } },
			{ id: 't2', type: 'llm', data: { config: {} } },
			{ id: 'e1', source: 's', target: 't1', sourceHandle: 'case_c1' }
		]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		onConnect({ source: 's', target: 't2', sourceHandle: 'case_c1' } as any);
		expect(elements.value.filter(el => 'source' in el)).toHaveLength(1);
		expect(snapped).toBe(0);
	});

	it('拒绝跨容器连线', () => {
		const elements = ref<any[]>([
			{ id: 'grp', type: 'loop_body_group', data: { config: {} } },
			{ id: 'inner', type: 'llm', parentNode: 'grp', data: { config: {} } },
			{ id: 'outer', type: 'llm', data: { config: {} } }
		]);
		let snapped = 0;
		const { onConnect } = useEdgeConnect(elements, t, () => snapped++);
		// inner（在 group 内）连 outer（主画布）→ parentNode 不同 → 拒绝
		onConnect({ source: 'inner', target: 'outer', sourceHandle: null } as any);
		expect(elements.value.filter(el => 'source' in el)).toHaveLength(0);
		expect(snapped).toBe(0);
	});
});
