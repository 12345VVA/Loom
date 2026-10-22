import type { ModuleConfig } from '/@/cool';

// 纯页面承载层：页面挂载走后端菜单（menu-route-viewpath.mdc），不在 config.ts 重复注册路由。
export default (): ModuleConfig => {
	return {
		order: 10,
		label: 'IP 资产库',
		description: '角色 / 场景 / 风格资产沉淀与组装协议'
	};
};
