import { type ModuleConfig } from '/@/cool';

// 定时任务模块：路由由后端菜单驱动（views/list.vue），此处仅注册模块本体。
export default (): ModuleConfig => {
	return {
		order: 8
	};
};
