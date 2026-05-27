import { type ModuleConfig } from '/@/cool';

export default (): ModuleConfig => {
	return {
		enable: true,
		components: [() => import('./components/codemirror.vue')],

		label: 'CodeMirror 编辑器',
		description: '基于 CodeMirror 6 封装的 JSON 代码编辑器',
		author: 'Loom',
		version: '1.0.0',
		updateTime: '2026-05-26',
		demo: [
			{
				name: '基础用法',
				component: () => import('./demo/base.vue')
			}
		],
		doc: 'https://codemirror.net'
	};
};
