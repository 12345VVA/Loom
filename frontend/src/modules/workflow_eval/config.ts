import { type ModuleConfig } from '/@/cool';

export default (): ModuleConfig => ({
	order: 9,
	views: [
		{
			path: '/workflow/eval/compare',
			meta: { keepAlive: false, label: '回归对比' },
			component: () => import('./views/compare.vue')
		}
	]
});
