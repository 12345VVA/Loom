import { describe, expect, it } from 'vitest';
import { planNodeRemoval } from '/$/workflow/composables/useNodeOps';

// 典型 loop 结构：controller + group(含 controllerNodeId) + group 内子节点 + 外部节点 + 连线
function loopFixture() {
	return [
		{ id: 'lc1', type: 'loop_controller', label: '循环', position: { x: 0, y: 0 }, data: { config: {} } },
		{
			id: 'grp1',
			type: 'loop_body_group',
			label: '循环体',
			position: { x: 100, y: 100 },
			data: { config: { controllerNodeId: 'lc1' } }
		},
		{
			id: 'c1',
			type: 'llm',
			label: '子',
			position: { x: 10, y: 20 },
			parentNode: 'grp1',
			expandParent: true,
			data: { config: {} }
		},
		{ id: 'other', type: 'llm', label: '其他', position: { x: 500, y: 500 }, data: { config: {} } },
		{ id: 'e1', source: 'lc1', target: 'c1', type: 'direct' },
		{ id: 'e2', source: 'c1', target: 'other', type: 'direct' }
	];
}

describe('planNodeRemoval', () => {
	// [P0 回归] 删 controller 必须连带其 loop_body_group，否则产生孤儿 group
	it('cascades: deleting loop_controller also removes its loop_body_group', () => {
		const ids = planNodeRemoval(loopFixture(), { nodeIds: ['lc1'] }).map(el => el.id);
		expect(ids).not.toContain('lc1');
		expect(ids).not.toContain('grp1');
	});

	it('cascades: deleting loop_body_group also removes its controller', () => {
		const ids = planNodeRemoval(loopFixture(), { nodeIds: ['grp1'] }).map(el => el.id);
		expect(ids).not.toContain('grp1');
		expect(ids).not.toContain('lc1');
	});

	// [P0 回归] 删 group 时子节点相对坐标必须转为绝对，否则渲染错乱
	it('converts child relative position to absolute when its group is removed', () => {
		const child = planNodeRemoval(loopFixture(), { nodeIds: ['grp1'] }).find(el => el.id === 'c1');
		expect(child).toBeDefined();
		expect(child.parentNode).toBeUndefined();
		expect(child.position).toEqual({ x: 110, y: 120 }); // 10+100, 20+100
	});

	it('removes edges touching the deleted node but keeps unrelated edges', () => {
		const edges = planNodeRemoval(loopFixture(), { nodeIds: ['other'] })
			.filter(el => 'source' in el)
			.map(el => el.id);
		expect(edges).not.toContain('e2'); // c1 -> other, touches 'other'
		expect(edges).toContain('e1'); // lc1 -> c1, untouched
	});

	it('supports explicit batch removal of nodes and edges', () => {
		const ids = planNodeRemoval(loopFixture(), { nodeIds: ['other'], edgeIds: ['e1'] }).map(el => el.id);
		expect(ids).not.toContain('other');
		expect(ids).not.toContain('e1'); // 显式删除的 edge
	});

	it('does not cascade-affect unrelated groups when deleting an ordinary node', () => {
		const ids = planNodeRemoval(loopFixture(), { nodeIds: ['other'] }).map(el => el.id);
		expect(ids).toContain('lc1');
		expect(ids).toContain('grp1');
	});
});
