import { type ModuleConfig } from '/@/cool';

export default (): ModuleConfig => {
	return {
		toolbar: {
			order: 20,
			component: import('./components/toolbar-notice.vue')
		},
		views: [
			{
				path: '/my/notification',
				meta: {
					label: '我的通知'
				},
				component: () => import('./views/my-notification.vue')
			}
		]
	};
};
