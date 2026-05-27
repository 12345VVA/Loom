import { type ModuleConfig } from '/@/cool';

export default (): ModuleConfig => {
	return {
		enable: true,
		components: [() => import('./components/markdown.vue')],

		label: 'Markdown 编辑器',
		description: '基于 md-editor-v3 封装的 Markdown 编辑器与渲染器',
		author: 'Loom',
		version: '1.0.0',
		updateTime: '2026-05-27',
		demo: [
			{
				name: '基础用法',
				component: () => import('./demo/base.vue')
			}
		],
		doc: 'https://imzbf.github.io/md-editor-v3'
	};
};
