import { type ModuleConfig } from '/@/cool';
import { useStore } from './store';
import { config } from '/@/config';
import { t } from '/@/plugins/i18n';
import './static/css/index.scss';

export default (): ModuleConfig => {
	return {
		order: 99,
		options: {
			index: '',
			api: ''
		},
		ignore: {
			NProgress: [
				'/base/open/eps',
				'/base/comm/person',
				'/base/comm/permmenu',
				'/base/comm/upload',
				'/base/comm/uploadMode'
			],
			token: ['/login', '/401', '/403', '/404', '/500', '/502']
		},
		components: Object.values(import.meta.glob('./components/**/*.{vue,tsx}')),
		views: [
			{
				path: '/my/info',
				meta: {
					label: t('个人中心')
				},
				component: () => import('./views/info.vue')
			}
		],
		pages: [
			{
				path: '/login',
				component: () => import('./pages/login/index.vue')
			},
			...['401', '403', '404', '500', '502'].map(code => {
				return {
					path: `/${code}`,
					meta: {
						process: false
					},
					component: () => import(`./pages/error/${code}.vue`)
				};
			})
		],
		install() {
			// 设置标题
			document.title = config.app.name;

			// 设置加载文案
			const loading = document.querySelector('#Loading');

			if (loading) {
				const name = loading.querySelector('.preload__name');
				const title = loading.querySelector('.preload__title');
				const subTitle = loading.querySelector('.preload__sub-title');

				if (name) {
					name.innerHTML = config.app.name;
				}
				if (title) {
					title.innerHTML = t('正在加载资源...');
				}
				if (subTitle) {
					subTitle.innerHTML = t('初次加载资源可能需要较多时间，请耐心等待');
				}
			}
		},
		async onLoad() {
			const { user, menu, app } = useStore();

			// token 事件
			async function hasToken(cb: () => Promise<any> | void) {
				if (cb) {
					app.addEvent('hasToken', cb);

					if (user.token) {
						await cb();
					}
				}
			}

			await hasToken(async () => {
				// 获取用户信息
				user.get();
				// 获取菜单权限
				await menu.get();
			});

			return {
				hasToken
			};
		}
	};
};
