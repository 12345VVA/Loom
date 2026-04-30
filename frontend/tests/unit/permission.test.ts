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

		expect(checkPerm('sys:user:add')).toBe(true);
		expect(checkPerm('sys:user:delete')).toBe(false);
	});

	it('checks or and and permission groups', () => {
		menu.perms = ['base:sys:user:add', 'base:sys:user:update'];

		expect(checkPerm({ or: ['sys:user:delete', 'sys:user:add'] })).toBe(true);
		expect(checkPerm({ and: ['sys:user:add', 'sys:user:update'] })).toBe(true);
		expect(checkPerm({ and: ['sys:user:add', 'sys:user:delete'] })).toBe(false);
	});

	it('checks mixed truthy and falsy group values', () => {
		menu.perms = ['base:sys:user:add'];

		expect(checkPerm({ or: ['', 'sys:user:add'] })).toBe(true);
		expect(checkPerm({ and: ['sys:user:add', ''] })).toBe(false);
	});
});
