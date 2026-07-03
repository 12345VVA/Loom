import { ModuleConfig } from '/@/cool';

export default (): ModuleConfig => ({
	enable: true,
	order: 10,
	views: [
		{
			path: '/workflow/annotation/annotation',
			meta: { label: '标注历史' },
			component: () => import('./views/annotation.vue')
		}
	],
	pages: [],
	components: [],
	onLoad() {},
	install() {}
});
