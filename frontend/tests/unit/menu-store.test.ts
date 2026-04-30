import { describe, expect, it, vi } from 'vitest';
import { useMenuStore } from '/$/base/store/menu';

vi.mock('/@/cool', () => {
	return {
		storage: {
			info: vi.fn(() => ({})),
			get: vi.fn(),
			set: vi.fn()
		},
		deepTree: (list: any[]) => {
			const result: any[] = [];
			const map: Record<number, any> = {};

			list
				.slice()
				.sort((a, b) => (a.orderNum || 0) - (b.orderNum || 0))
				.forEach(item => {
					map[item.id] = item;
					const parent = map[item.parentId];

					if (parent) {
						(parent.children || (parent.children = [])).push(item);
					} else {
						result.push(item);
					}
				});

			return result;
		},
		revDeepTree: vi.fn(),
		router: {
			del: vi.fn(),
			clear: vi.fn(),
			push: vi.fn()
		},
		service: {
			base: {
				comm: {
					permmenu: vi.fn(() =>
						Promise.resolve({
							menus: [
								{
									id: 1,
									name: '系统管理',
									type: 0,
									router: '/base',
									orderNum: 10,
									isShow: true
								},
								{
									id: 2,
									parentId: 1,
									name: '用户管理',
									type: 1,
									router: 'base/sys/user',
									viewPath: 'modules/base/views/user/index.vue',
									keepAlive: true,
									orderNum: 11
								},
								{
									id: 3,
									parentId: 2,
									name: '新增用户',
									type: 2,
									perms: 'base:sys:user:add'
								},
								{
									id: 4,
									parentId: 1,
									name: '字典管理',
									type: 1,
									router: 'dict/list',
									viewPath: 'modules/dict/views/list.vue',
									isShow: false,
									orderNum: 12
								}
							],
							perms: ['base:sys:user:add']
						})
					)
				}
			}
		}
	};
});

describe('menu store', () => {
	it('returns the first menu path from grouped menus', () => {
		const menu = useMenuStore();

		expect(
			menu.getPath([
				{
					type: 0,
					path: '/group',
					children: [{ type: 1, path: '/base/sys/user' }]
				}
			] as any)
		).toBe('/base/sys/user');
	});

	it('sets grouped menu state from flat backend menus', () => {
		const menu = useMenuStore();

		menu.setGroup([
			{ id: 1, parentId: 0, name: '系统管理', type: 0, orderNum: 10, isShow: true },
			{ id: 2, parentId: 1, name: '用户管理', type: 1, path: '/base/sys/user', orderNum: 11 }
		] as any);

		expect(menu.group).toHaveLength(1);
		expect(menu.group[0].children?.[0].path).toBe('/base/sys/user');
	});

	it('converts backend menu data to frontend routes and permissions', async () => {
		const menu = useMenuStore();

		await menu.get();

		expect(menu.all).toHaveLength(4);
		expect(menu.perms).toEqual(['base:sys:user:add']);
		expect(menu.group[0].children?.[0]).toMatchObject({
			path: '/',
			isShow: true,
			meta: {
				label: '用户管理',
				keepAlive: true
			}
		});
		expect(menu.group[0].children?.[1]).toMatchObject({
			path: '/dict/list',
			isShow: false,
			meta: {
				label: '字典管理',
				keepAlive: 0
			}
		});
		expect(menu.list.map(e => e.path)).toEqual(['/base']);
		expect(menu.routes).toHaveLength(3);
		expect(menu.routes[0]).toMatchObject({
			path: '/',
			name: 'home',
			viewPath: 'modules/base/views/user/index.vue'
		});
		expect(menu.routes[1]).toMatchObject({
			path: '/dict/list',
			viewPath: 'modules/dict/views/list.vue'
		});
		expect(menu.routes[2]).toMatchObject({
			path: '/base/sys/user',
			name: 'homeRedirect',
			redirect: '/'
		});
	});
});
