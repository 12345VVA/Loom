import { describe, expect, it } from 'vitest';
import { hitTestGroup } from '/$/workflow/utils/group-hit-test';

describe('hitTestGroup', () => {
	const groups = [
		{
			id: 'g1',
			type: 'loop_body_group',
			position: { x: 100, y: 100 },
			style: { width: '400px', height: '250px' }
		},
		{
			id: 'g2',
			type: 'loop_body_group',
			position: { x: 600, y: 200 },
			style: { width: '300px', height: '200px' }
		}
	];

	it('点落在 group 内时返回该 group 的矩形', () => {
		const hit = hitTestGroup(groups, 200, 150);
		expect(hit?.id).toBe('g1');
		expect(hit).toMatchObject({ x: 100, y: 100, width: 400, height: 250 });
	});

	it('点在 group 边界上算命中（含左上角与右下角）', () => {
		expect(hitTestGroup(groups, 100, 100)?.id).toBe('g1'); // 左上角
		expect(hitTestGroup(groups, 500, 350)?.id).toBe('g1'); // 右下角 100+400, 100+250
	});

	it('点落在 group 间隙时返回 undefined', () => {
		expect(hitTestGroup(groups, 550, 150)).toBeUndefined();
	});

	it('多 group 重叠时返回数组中首个命中的', () => {
		const overlapping = [
			{
				id: 'first',
				type: 'loop_body_group',
				position: { x: 0, y: 0 },
				style: { width: '100px', height: '100px' }
			},
			{
				id: 'second',
				type: 'loop_body_group',
				position: { x: 0, y: 0 },
				style: { width: '100px', height: '100px' }
			}
		];
		expect(hitTestGroup(overlapping, 50, 50)?.id).toBe('first');
	});

	it('忽略非 group 节点与边', () => {
		const els = [
			{ id: 'n1', type: 'llm', position: { x: 0, y: 0 } },
			{ id: 'e1', source: 'a', target: 'b' },
			{
				id: 'g1',
				type: 'loop_body_group',
				position: { x: 0, y: 0 },
				style: { width: '100px', height: '100px' }
			}
		];
		expect(hitTestGroup(els, 50, 50)?.id).toBe('g1');
	});

	it('缺省宽高时按 400×250 判定', () => {
		const els = [{ id: 'g1', type: 'loop_body_group', position: { x: 0, y: 0 } }];
		expect(hitTestGroup(els, 300, 200)?.id).toBe('g1'); // 在 400×250 内
		expect(hitTestGroup(els, 450, 300)).toBeUndefined(); // 超出缺省
	});
});
