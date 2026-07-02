import { describe, expect, it } from 'vitest';
import { validateGraph } from '/$/workflow/composables/useSaveFlow';

// 本项目 i18n key 即中文，identity t 直接回传 key 便于断言
const t = (k: string) => k;

function node(id: string, type: string, opts: any = {}) {
	return {
		id,
		type,
		label: opts.label || id,
		parentNode: opts.parentNode,
		data: { config: opts.config || {} }
	};
}
function edge(source: string, target: string) {
	return { source, target };
}
function hasWarning(warnings: string[], fragment: string) {
	return warnings.some(w => w.includes(fragment));
}

describe('validateGraph', () => {
	it('passes (no warnings) for a minimal well-formed graph', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end', { config: { outputTemplate: '{{result}}' } }),
			node('llm', 'llm', { config: { modelProfileCode: 'p1', outputVariable: 'x' } })
		];
		const edges = [edge('s', 'llm'), edge('llm', 'e')];
		expect(validateGraph(nodes, edges, t)).toEqual([]);
	});

	it('warns when the graph has no start node', () => {
		const nodes = [node('e', 'end'), node('llm', 'llm', { config: { modelProfileCode: 'p1' } })];
		const edges = [edge('llm', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), '开始节点')).toBe(true);
	});

	it('warns when the graph has multiple start nodes', () => {
		const nodes = [node('s1', 'start'), node('s2', 'start'), node('e', 'end')];
		const edges = [edge('s1', 'e'), edge('s2', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), '多个')).toBe(true);
	});

	it('warns about isolated nodes that have no connections', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end'),
			node('orphan', 'llm', { config: { modelProfileCode: 'p1' } })
		];
		const edges = [edge('s', 'e')]; // orphan 既无入边也无出边
		expect(hasWarning(validateGraph(nodes, edges, t), '孤立')).toBe(true);
	});

	it('warns when a model node (llm) is missing its profile', () => {
		const nodes = [node('s', 'start'), node('e', 'end'), node('llm', 'llm', {})];
		const edges = [edge('s', 'llm'), edge('llm', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), 'Profile')).toBe(true);
	});

	it('warns when a switch node has no matching variable', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end'),
			node('sw', 'switch', { config: { cases: [{ value: 'a' }] } })
		];
		const edges = [edge('s', 'sw'), edge('sw', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), '匹配变量名')).toBe(true);
	});

	it('warns when a switch case has a blank value', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end'),
			node('sw', 'switch', { config: { variable: 'x', cases: [{ value: '' }, { value: 'a' }] } })
		];
		const edges = [edge('s', 'sw'), edge('sw', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), 'Case')).toBe(true);
	});

	it('warns when an end node (non-json mode) lacks outputTemplate', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end', { config: { outputFormat: 'text' } }),
			node('llm', 'llm', { config: { modelProfileCode: 'p1' } })
		];
		const edges = [edge('s', 'llm'), edge('llm', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), '输出结构模板')).toBe(true);
	});

	it('warns when a loop container has multiple entry nodes inside', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end'),
			node('grp', 'loop_body_group'),
			node('c1', 'llm', { config: { modelProfileCode: 'p1' }, parentNode: 'grp' }),
			node('c2', 'llm', { config: { modelProfileCode: 'p2' }, parentNode: 'grp' })
		];
		// c1、c2 都在容器内且互不连线 → 各自是无输入起点
		const edges = [edge('s', 'grp'), edge('grp', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), '多个没有输入')).toBe(true);
	});

	it('warns when two non-exclusive nodes share the same outputVariable', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end'),
			node('l1', 'llm', { config: { modelProfileCode: 'p1', outputVariable: 'result' } }),
			node('l2', 'llm', { config: { modelProfileCode: 'p2', outputVariable: 'result' } })
		];
		// l1、l2 分属两条独立链（非条件分支互斥），同名 outputVariable 应告警
		const edges = [edge('s', 'l1'), edge('l1', 'e'), edge('s', 'l2'), edge('l2', 'e')];
		expect(hasWarning(validateGraph(nodes, edges, t), '输出变量名重复')).toBe(true);
	});

	it('does NOT warn when same outputVariable is on exclusive condition branches', () => {
		const nodes = [
			node('s', 'start'),
			node('e', 'end'),
			node('cond', 'condition'),
			node('t', 'llm', { config: { modelProfileCode: 'p1', outputVariable: 'result' } }),
			node('f', 'llm', { config: { modelProfileCode: 'p2', outputVariable: 'result' } })
		];
		// cond 的两个下游 t/f 互斥（同一条件节点不同分支），同名 outputVariable 不应告警
		const edges = [
			edge('s', 'cond'),
			edge('cond', 't'),
			edge('cond', 'f'),
			edge('t', 'e'),
			edge('f', 'e')
		];
		expect(hasWarning(validateGraph(nodes, edges, t), '输出变量名重复')).toBe(false);
	});
});
