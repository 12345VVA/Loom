declare module '*.vue' {
	import type { DefineComponent } from 'vue';
	const component: DefineComponent<{}, {}, any>;

	export default component;
}

declare module 'element-plus/dist/locale/zh-cn.mjs';

// 实体类型别名：指向 build/cool/eps.d.ts 生成的实体接口（接口本体由生成器维护）
declare namespace Eps {
	type BaseSysUserEntity = user;
	type BaseSysMenuEntity = menu;
	type BaseSysDepartmentEntity = department;
	type TaskInfoEntity = TaskInfo;
}
