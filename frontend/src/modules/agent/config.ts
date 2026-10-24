import type { ModuleConfig } from '/@/cool';

// 纯页面承载层：页面挂载走后端菜单（menu-route-viewpath.mdc），不在 config.ts 重复注册路由。
export default (): ModuleConfig => {
	return {
		order: 11,
		label: '智能体',
		description: 'LangGraph 智能体运行时（SPI 工具注册 + 发布快照 + 会话观测）',
		// 全局悬浮 AI 助手（cool/index.vue 按 index 注入主框架）
		index: {
			component: import('./components/assistant-ball.vue')
		}
	};
};
