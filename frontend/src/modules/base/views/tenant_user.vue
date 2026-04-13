<template>
	<cl-crud ref="Crud">
		<cl-row>
			<!-- 刷新按钮 -->
			<cl-refresh-btn />
			<!-- 新增按钮 -->
			<cl-add-btn />
			<!-- 删除按钮 -->
			<cl-multi-delete-btn />
			<cl-flex1 />
			<!-- 条件搜索 -->
			<cl-search ref="Search" />
		</cl-row>

		<cl-row>
			<!-- 数据表格 -->
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<!-- 分页控件 -->
			<cl-pagination />
		</cl-row>

		<!-- 新增、编辑 -->
		<cl-upsert ref="Upsert" />
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: "base-sys-tenant_user",
});

import { useCrud, useTable, useUpsert, useSearch } from "@cool-vue/crud";
import { useCool } from "/@/cool";
import { useI18n } from "vue-i18n";
import { reactive } from "vue";

const { service } = useCool();
const { t } = useI18n();

// 选项
const options = reactive({
	status: [
		{ label: t("禁用"), value: 0, type: "danger" },
		{ label: t("启用"), value: 1, type: "success" },
	],
});

// cl-upsert
const Upsert = useUpsert({
	items: [
		{
			label: t("租户标识"),
			prop: "tenantCode",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			required: true,
		},
		{
			label: t("用户名"),
			prop: "username",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			required: true,
		},
		{
			label: t("姓名"),
			prop: "name",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("昵称"),
			prop: "nickName",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("手机号"),
			prop: "phone",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			required: true,
		},
		{
			label: t("邮箱"),
			prop: "email",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("头像"),
			prop: "headImg",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("性别"),
			prop: "gender",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("备注"),
			prop: "remark",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("扩展信息"),
			prop: "extraInfo",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("状态"),
			prop: "status",
			component: { name: "el-radio-group", options: options.status },
			value: 1,
			required: true,
		},
	],
});

// cl-table
const Table = useTable({
	columns: [
		{ type: "selection" },
		{ label: t("租户标识"), prop: "tenantCode", minWidth: 120 },
		{ label: t("用户名"), prop: "username", minWidth: 120 },
		{ label: t("姓名"), prop: "name", minWidth: 120 },
		{ label: t("昵称"), prop: "nickName", minWidth: 120 },
		{ label: t("手机号"), prop: "phone", minWidth: 120 },
		{ label: t("邮箱"), prop: "email", minWidth: 120 },
		{ label: t("头像"), prop: "headImg", minWidth: 120 },
		{ label: t("性别"), prop: "gender", minWidth: 120 },
		{ label: t("备注"), prop: "remark", minWidth: 120 },
		{ label: t("扩展信息"), prop: "extraInfo", minWidth: 120 },
		{
			label: t("状态"),
			prop: "status",
			minWidth: 120,
			dict: options.status,
		},
		{
			label: t("创建时间"),
			prop: "createTime",
			minWidth: 170,
			sortable: "desc",
			component: { name: "cl-date-text" },
		},
		{
			label: t("更新时间"),
			prop: "updateTime",
			minWidth: 170,
			sortable: "custom",
			component: { name: "cl-date-text" },
		},
		{ type: "op", buttons: ["edit", "delete"] },
	],
});

// cl-search
const Search = useSearch();

// cl-crud
const Crud = useCrud(
	{
		service: service.base.sys.tenant_user,
	},
	(app) => {
		app.refresh();
	},
);

// 刷新
function refresh(params?: any) {
	Crud.value?.refresh(params);
}
</script>
