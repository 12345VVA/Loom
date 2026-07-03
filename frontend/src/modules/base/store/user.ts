import { defineStore } from 'pinia';
import { ref } from 'vue';
import { storage } from '/@/cool/utils';
import { service, router } from '/@/cool';
import { useMenuStore } from './menu';
import { useProcessStore } from './process';

// 初始化数据：userInfo 仍从 localStorage 读取（非敏感）
// token 从 sessionStorage 读取（页面刷新可恢复，关闭标签页失效）
const initialUserInfo = storage.get('userInfo');
const initialToken = storage.session.get('token');

export const useUserStore = defineStore('user', function () {
	// 标识
	const token = ref<string>(initialToken || '');

	// 设置标识
	function setToken(data: {
		token: string;
		expire: number;
		// refreshToken 现通过 HttpOnly cookie 传递，前端不再存储
		// 保留字段以兼容旧调用方（如 dev-tools），但不再持久化
		refreshToken?: string;
		refreshExpire?: number;
	}) {
		// 请求的唯一标识
		token.value = data.token;
		// token 改存 sessionStorage：XSS 无法持久窃取，关闭标签页即失效
		storage.session.set('token', data.token, data.expire);
	}

	// 刷新标识
	async function refreshToken(): Promise<string> {
		return new Promise((resolve, reject) => {
			// refreshToken 通过 HttpOnly cookie 自动携带，无需前端传参
			service.base.open
				.refreshToken({})
				.then(res => {
					setToken(res);
					resolve(res.token);
				})
				.catch(err => {
					logout();
					reject(err);
				});
		});
	}

	// 用户信息
	const info = ref<Eps.BaseSysUserEntity | null>(initialUserInfo);

	// 设置用户信息
	function set(value: any) {
		info.value = value;
		// userInfo 非敏感，仍存 localStorage
		storage.set('userInfo', value);
	}

	// 清除用户
	function clear() {
		storage.remove('userInfo');
		// 清除 sessionStorage 中的 token
		storage.session.remove('token');
		token.value = '';
		info.value = null;
	}

	// 退出
	async function logout() {
		// 重置菜单与进程 store，避免登出后残留上一个用户的菜单/标签数据
		const menu = useMenuStore();
		const process = useProcessStore();
		menu.$reset();
		process.$reset();

		// 清除菜单相关的本地存储，防止刷新后恢复旧数据
		storage.remove('base.menuGroup');
		storage.remove('base.menuPerms');

		clear();
		router.clear();
		router.push('/login');
	}

	// 获取用户信息
	async function get() {
		return service.base.comm.person().then(res => {
			set(res);
			return res;
		});
	}

	return {
		token,
		info,
		get,
		set,
		logout,
		clear,
		setToken,
		refreshToken
	};
});
