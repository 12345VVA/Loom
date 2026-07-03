import { useStore } from '../store';
import { isObject } from 'lodash-es';

/**
 * 权限段前缀匹配：stored === required，或 stored 以 required 为段前缀（后接 ":"）。
 *
 * 用于替代 String.includes 子串匹配——后者会让 required="base:sys:role" 误命中
 * stored="base:sys:roles:add"（前者是后者的字符前缀）。段前缀要求边界对齐到 ":"，
 * 天然避免 role/roles、move/moveAll 等兄弟资源/动作的误匹配。
 *
 * 设计语义：“持有子权限可通过父级校验”——当 stored 是 required 的子权限时（如
 * stored="base:sys:role:add" 满足 required="base:sys:role"），校验通过。这是**期望的
 * 设计**，适用于“页面可见性”场景：用户只要持有任一子操作权限（add/update/delete 等）就
 * 能看到该页面，避免无权限页面残留在导航中。
 *
 * 适用边界：本函数仅用于页面级/路由级权限校验（如 router.beforeEach 的 to.meta.permission
 * 校验）。**按钮级权限校验应使用精确匹配 `stored === required`，不使用 permMatches**——
 * 按钮可见性需严格对齐到具体动作权限，不应被同前缀的兄弟权限或更细粒度的子权限误触发。
 */
export function permMatches(stored: string, required: string): boolean {
	return stored === required || stored.startsWith(`${required}:`);
}

function parse(value: any) {
	const { menu } = useStore();

	if (typeof value == 'string') {
		const v = value.replace(/\s/g, '');
		return v ? menu.perms.some((e: any) => typeof e === 'string' && permMatches(e, v)) : false;
	} else {
		return Boolean(value);
	}
}

export function checkPerm(value: string | { or?: string[]; and?: string[] }) {
	if (!value) {
		return false;
	}

	if (isObject(value)) {
		if (value.or) {
			return value.or.some(parse);
		}

		if (value.and) {
			return value.and.some((e: any) => !parse(e)) ? false : true;
		}
	}

	return parse(value);
}
