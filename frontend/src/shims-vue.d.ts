declare module '*.vue' {
	import type { DefineComponent } from 'vue';
	const component: DefineComponent<{}, {}, any>;

	export default component;
}

declare module 'element-plus/dist/locale/zh-cn.mjs';

declare namespace Eps {
	type BaseSysUserEntity = user;
	type BaseSysMenuEntity = menu;
	type BaseSysDepartmentEntity = department;
	type TaskInfoEntity = TaskInfo;

	interface BaseSysDepartment {
		add(data?: any): Promise<any>;
		update(data?: any): Promise<any>;
		list(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
		info(data?: any): Promise<any>;
		delete(data?: any): Promise<any>;
	}

	interface BaseSysMenu {
		add(data?: any): Promise<any>;
		update(data?: any): Promise<any>;
		list(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
		info(data?: any): Promise<any>;
		delete(data?: any): Promise<any>;
		export(data?: any): Promise<any>;
		import(data?: any): Promise<any>;
		create(data?: any): Promise<any>;
		parse(data?: any): Promise<any>;
	}

	interface BaseSysUser {
		add(data?: any): Promise<any>;
		update(data?: any): Promise<any>;
		list(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
		info(data?: any): Promise<any>;
		delete(data?: any): Promise<any>;
	}

	interface BaseSysRole {
		add(data?: any): Promise<any>;
		update(data?: any): Promise<any>;
		list(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
		info(data?: any): Promise<any>;
		delete(data?: any): Promise<any>;
	}

	interface DictInfo {
		list(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
		data(data?: any): Promise<any>;
		types(data?: any): Promise<any>;
	}

	interface DictType {
		list(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
	}

	interface TaskInfo {
		add(data?: any): Promise<any>;
		update(data?: any): Promise<any>;
		delete(data?: any): Promise<any>;
		page(data?: any): Promise<any>;
		list(data?: any): Promise<any>;
	}
}
