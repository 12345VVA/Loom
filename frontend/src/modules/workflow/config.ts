import type { ModuleConfig } from '/@/cool';

export default (): ModuleConfig => {
	return {
		order: 8,
		views: [
			{
				path: '/workflow/editor',
				meta: {
					keepAlive: false,
					label: '工作流设计器'
				},
				component: () => import('./views/editor.vue')
			}
		],
		onLoad() {
			// 前端模块挂载时的生命周期回调，无需特殊初始化
		}
	};
};
