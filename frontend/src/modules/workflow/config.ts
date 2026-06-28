import type { ModuleConfig } from '/@/cool';

export default (): ModuleConfig => {
	return {
		order: 8,
		views: [],
		onLoad() {
			// 前端模块挂载时的生命周期回调，无需特殊初始化
		}
	};
};
