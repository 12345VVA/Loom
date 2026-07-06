const DEVICE_ID_KEY = 'deviceId';

let memDeviceId: string | null = null;

function generateId(): string {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return crypto.randomUUID();
	}
	return 'd-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

/**
 * 获取本设备持久标识：首次访问生成 uuid 存 localStorage，之后稳定返回同一值。
 *
 * 用途：随请求头 X-Device-Id 上送后端，供"设备管理"按设备聚合同一浏览器的多次登录
 * （参考谷歌账户设备活动）。同浏览器多次登录会被聚合成一条设备记录，而非多行会话。
 * 仅本应用同源使用，不跨站点、不联网上报。
 */
export function getDeviceId(): string {
	try {
		let id = localStorage.getItem(DEVICE_ID_KEY);
		if (!id) {
			id = generateId();
			localStorage.setItem(DEVICE_ID_KEY, id);
		}
		return id;
	} catch {
		// localStorage 不可用（隐私模式等）时，退化为本次会话稳定的内存值
		if (!memDeviceId) {
			memDeviceId = generateId();
		}
		return memDeviceId;
	}
}
