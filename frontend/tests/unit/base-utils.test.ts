import { describe, expect, it } from 'vitest';
import { vi } from 'vitest';
import { revisePath } from '/$/base/utils';
import { deepTree, revDeepTree } from '/@/cool/utils';

vi.mock('/$/base/utils/permission', () => ({
	checkPerm: vi.fn()
}));

describe('base utils', () => {
	it('normalizes backend menu router paths', () => {
		expect(revisePath('base/sys/user')).toBe('/base/sys/user');
		expect(revisePath('/dict/list')).toBe('/dict/list');
		expect(revisePath('')).toBe('');
	});

	it('builds a menu tree by parentId and orderNum', () => {
		const tree = deepTree([
			{ id: 2, parentId: 1, name: 'child', orderNum: 2 },
			{ id: 1, parentId: 0, name: 'root', orderNum: 1 }
		]);

		expect(tree).toHaveLength(1);
		expect(tree[0].children[0].name).toBe('child');
	});

	it('flattens custom menu trees with generated ids', () => {
		const list = revDeepTree([
			{
				name: 'system',
				children: [{ name: 'user' }]
			}
		]);

		expect(list).toHaveLength(2);
		expect(list[1].parentId).toBe(list[0].id);
	});
});
