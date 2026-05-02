<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'notification-rule'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const Upsert = useUpsert({
	dialog: { width: '720px' },
	props: { labelWidth: '110px' },
	items: [
		{ label: t('编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{ label: t('用户ID'), prop: 'users', component: { name: 'el-input' } },
		{ label: t('角色'), prop: 'roles', component: { name: 'el-input' } },
		{ label: t('部门ID'), prop: 'departments', component: { name: 'el-input' } },
		{ label: t('租户ID'), prop: 'tenants', component: { name: 'el-input' } },
		{ label: t('包含子部门'), prop: 'includeChildDepartments', value: true, component: { name: 'el-switch' } },
		{ label: t('全体管理员'), prop: 'allAdmins', value: false, component: { name: 'el-switch' } },
		{ label: t('安全条件'), prop: 'condition', component: { name: 'el-input' } },
		{ label: t('启用'), prop: 'isActive', value: true, component: { name: 'el-switch' } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('编码'), prop: 'code', minWidth: 180 },
		{ label: t('名称'), prop: 'name', minWidth: 160 },
		{ label: t('全体管理员'), prop: 'allAdmins', width: 120 },
		{ label: t('安全条件'), prop: 'condition', minWidth: 150 },
		{ label: t('启用'), prop: 'isActive', width: 100 },
		{ type: 'op', buttons: ['edit', 'delete'] }
	]
});

useCrud(
	{
		service: service.notification.rule
	},
	app => {
		app.refresh();
	}
);
</script>
