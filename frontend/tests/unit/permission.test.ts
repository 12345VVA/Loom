import { describe, expect, it } from 'vitest';
import { vi } from 'vitest';
import { checkPerm } from '/$/base/utils/permission';

const menu = {
	perms: [] as string[]
};

vi.mock('/$/base/store', () => ({
	useStore: () => ({
		menu
	})
}));

describe('permission utils', () => {
	it('rejects empty permission inputs', () => {
		menu.perms = ['base:sys:user:add'];

		expect(checkPerm('')).toBe(false);
		expect(checkPerm({ or: [] })).toBe(false);
		expect(checkPerm({ and: [] })).toBe(true);
	});

	it('checks a single permission fragment', () => {
		menu.perms = ['base:sys:user:add', 'base:sys:user:update'];

		expect(checkPerm('base:sys:user:add')).toBe(true);
		expect(checkPerm('base:sys:user:delete')).toBe(false);
		// 省略 scope 前缀的形态不匹配：permMatches 要求段对齐（stored/required 完整可比）
		expect(checkPerm('sys:user:add')).toBe(false);
	});

	it('checks or and and permission groups', () => {
		menu.perms = ['base:sys:user:add', 'base:sys:user:update'];

		expect(checkPerm({ or: ['base:sys:user:delete', 'base:sys:user:add'] })).toBe(true);
		expect(checkPerm({ and: ['base:sys:user:add', 'base:sys:user:update'] })).toBe(true);
		expect(checkPerm({ and: ['base:sys:user:add', 'base:sys:user:delete'] })).toBe(false);
	});

	it('checks mixed truthy and falsy group values', () => {
		menu.perms = ['base:sys:user:add'];

		expect(checkPerm({ or: ['', 'base:sys:user:add'] })).toBe(true);
		expect(checkPerm({ and: ['base:sys:user:add', ''] })).toBe(false);
	});

	it('treats held child permission as satisfying parent-level check', () => {
		// 页面可见性语义：持有任一子操作权限即可通过父级（路由级）校验（见 permMatches docstring）
		menu.perms = ['base:sys:user:add'];

		expect(checkPerm('base:sys:user')).toBe(true);
	});

	it('does not substring-match sibling resources (role vs roles)', () => {
		// 段前缀匹配回归防护：String.includes 会让 required="base:sys:role" 误命中
		// stored="base:sys:roles:add"（重构为段对齐的核心动机）
		menu.perms = ['base:sys:roles:add'];

		expect(checkPerm('base:sys:role')).toBe(false);
		expect(checkPerm('base:sys:roles')).toBe(true);
	});
});
