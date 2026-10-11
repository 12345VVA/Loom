import { type ModuleConfig } from '/@/cool';
import { createI18n } from 'vue-i18n';
import messages from '@intlify/unplugin-vue-i18n/messages';
import { config } from '/@/config';

// 实例提升到模块级导出：非组件上下文（utils/*.ts 工具函数）也能经 i18n.global.t 取译文
export const i18n = createI18n({
	legacy: false,
	globalInjection: true,
	locale: config.i18n.locale,
	fallbackLocale: 'zh-cn',
	messages
});

export default (): ModuleConfig => {
	return {
		order: 100,
		toolbar: {
			component: import('./components/switch.vue')
		},
		install(app) {
			app.use(i18n);
		},

		label: 'i18n',
		description: '国际化组件',
		author: 'Loom',
		version: '1.0.0',
		updateTime: '2025-01-11',
		doc: 'https://github.com/intlify/vue-i18n'
	};
};
