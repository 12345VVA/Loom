import store from 'store';

export default {
	// 后缀标识
	suffix: '_deadtime',

	/**
	 * 获取
	 * @param {string} key 关键字
	 */
	get(key: string) {
		return store.get(key);
	},

	/**
	 * token 专用存储：基于 sessionStorage
	 * - 页面刷新仍可恢复
	 * - 关闭标签页即失效，降低 XSS 凭证失窃风险
	 * - refreshToken 不再前端存储，由后端 HttpOnly cookie 管理
	 */
	session: {
		suffix: '_deadtime',

		/**
		 * 获取
		 * @param key 关键字
		 */
		get(key: string): string | null {
			try {
				return window.sessionStorage.getItem(key);
			} catch {
				return null;
			}
		},

		/**
		 * 设置
		 * @param key 关键字
		 * @param value 值
		 * @param expires 过期时间（秒）
		 */
		set(key: string, value: string, expires?: number) {
			try {
				window.sessionStorage.setItem(key, value);
				if (expires) {
					window.sessionStorage.setItem(
						`${key}${this.suffix}`,
						String(Date.now() + expires * 1000)
					);
				}
			} catch {
				// sessionStorage 写入失败（如隐私模式）忽略，不影响主流程
			}
		},

		/**
		 * 是否过期
		 * @param key 关键字
		 */
		isExpired(key: string): boolean {
			const expiration = this.getExpiration(key);
			if (expiration === null) {
				// 未设置过期时间视为未过期
				return false;
			}
			return Number(expiration) - Date.now() <= 2000;
		},

		/**
		 * 获取到期时间
		 * @param key 关键字
		 */
		getExpiration(key: string): string | null {
			try {
				return window.sessionStorage.getItem(key + this.suffix);
			} catch {
				return null;
			}
		},

		/**
		 * 移除
		 * @param key 关键字
		 */
		remove(key: string) {
			try {
				window.sessionStorage.removeItem(key);
				window.sessionStorage.removeItem(key + this.suffix);
			} catch {
				// 忽略
			}
		}
	},

	/**
	 * 获取全部
	 */
	info() {
		const data: Record<string, any> = {};

		store.each((value: any, key: any) => {
			data[key] = value;
		});

		return data;
	},

	/**
	 * 设置
	 * @param {string} key 关键字
	 * @param {*} value 值
	 * @param {number} expires 过期时间
	 */
	set(key: string, value: any, expires?: number) {
		store.set(key, value);

		if (expires) {
			const expirationTime = Date.now() + expires * 1000;
			store.set(`${key}${this.suffix}`, expirationTime);
		}
	},

	/**
	 * 是否过期
	 * @param {string} key 关键字
	 */
	isExpired(key: string) {
		const expiration = this.getExpiration(key) || 0;
		return expiration - Date.now() <= 2000;
	},

	/**
	 * 获取到期时间
	 * @param {string} key 关键字
	 */
	getExpiration(key: string) {
		return this.get(key + this.suffix);
	},

	/**
	 * 移除
	 * @param {string} key 关键字
	 */
	remove(key: string) {
		store.remove(key);
		this.removeExpiration(key);
	},

	/**
	 * 移除到期时间
	 * @param {string} key 关键字
	 */
	removeExpiration(key: string) {
		store.remove(key + this.suffix);
	},

	/**
	 * 清理
	 */
	clearAll() {
		store.clearAll();
	}
};
