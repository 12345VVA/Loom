import { describe, expect, it, vi } from 'vitest';
import { useDictStore } from '/$/dict/store/dict';
import { deepFind, isEmpty } from '/$/dict/utils';

const mocks = vi.hoisted(() => ({
	dictData: vi.fn()
}));

vi.mock('/@/cool', () => ({
	storage: {
		get: vi.fn()
	},
	service: {
		dict: {
			info: {
				data: mocks.dictData
			}
		}
	}
}));

vi.mock('/@/cool/utils', () => ({
	deepTree: (list: any[], sort: 'asc' | 'desc' = 'asc') => {
		const result: any[] = [];
		const map: Record<number, any> = {};
		const sorted = list.slice().sort((a, b) => {
			const diff = (a.orderNum || 0) - (b.orderNum || 0);
			return sort === 'desc' ? -diff : diff;
		});

		sorted.forEach(item => {
			map[item.id] = item;
			const parent = map[item.parentId];

			if (parent) {
				(parent.children || (parent.children = [])).push(item);
			} else {
				result.push(item);
			}
		});

		return result;
	}
}));

vi.mock('/@/config', () => ({
	isDev: false
}));

describe('dict store and utils', () => {
	it('finds nested dict items with hierarchical labels', () => {
		const item = deepFind(2, [
			{
				label: '父级',
				value: 1,
				children: [{ label: '子级', value: 2 }]
			}
		]);

		expect(item).toMatchObject({
			value: 2,
			label: '父级 / 子级'
		});
		expect(deepFind(2, item ? [item] : [], { allLevels: false })).toMatchObject({ value: 2 });
	});

	it('treats empty string null and undefined as empty only', () => {
		expect(isEmpty('')).toBe(true);
		expect(isEmpty(null)).toBe(true);
		expect(isEmpty(undefined)).toBe(true);
		expect(isEmpty(0)).toBe(false);
		expect(isEmpty(false)).toBe(false);
	});

	it('refreshes dict data, fills labels and filters empty type names', async () => {
		mocks.dictData.mockResolvedValueOnce({
			status: [
				{ id: 1, name: '启用', value: '', orderNum: 1 },
				{ id: 2, name: '禁用', value: 0, orderNum: 2 }
			]
		});
		const dict = useDictStore();

		await dict.refresh(['status', '', undefined as any]);

		expect(mocks.dictData).toHaveBeenCalledWith({ types: ['status'] });
		expect(dict.get('status').value.map(e => e.label)).toEqual(['启用', '禁用']);
		expect(dict.find('status', [1, 0]).map(e => e?.label)).toEqual(['启用', '禁用']);
	});
});
