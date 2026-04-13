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
	name: "base-sys-tenant",
});

import { useCrud, useTable, useUpsert, useSearch } from "@cool-vue/crud";
import { useCool } from "/@/cool";
import { useI18n } from "vue-i18n";

const { service } = useCool();
const { t } = useI18n();

// 状态选项
const statusOptions = [
	{ label: "启用", value: 1, type: "success" },
	{ label: "禁用", value: 0, type: "danger" },
];

// 电话校验
const phoneValidator = (_rule: any, value: string, callback: any) => {
	if (!value) return callback();
	const phoneReg = /^1[3-9]\d{9}$/;
	const telReg = /^0\d{2,3}-?\d{7,8}$/;
	if (phoneReg.test(value) || telReg.test(value)) {
		callback();
	} else {
		callback(new Error("请输入正确的电话号码"));
	}
};

// 邮箱校验
const emailValidator = (_rule: any, value: string, callback: any) => {
	if (!value) return callback();
	const emailReg = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
	if (emailReg.test(value)) {
		callback();
	} else {
		callback(new Error("请输入正确的邮箱地址"));
	}
};

// cl-upsert
const Upsert = useUpsert({
	items: [
		{
			label: t("租户名称"),
			prop: "name",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			required: true,
		},
		// 编辑时显示且只读
		() => ({
			label: t("租户标识"),
			prop: "tenantCode",
			component: {
				name: "el-input",
				props: { disabled: Upsert.value?.mode === "update" },
			},
			span: 12,
			required: true,
			hidden: Upsert.value?.mode !== "update",
		}),
		{
			label: t("域名"),
			prop: "domain",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			required: true,
		},
		// 编辑时显示且只读
		() => ({
			label: t("AppId"),
			prop: "appId",
			component: {
				name: "el-input",
				props: { disabled: Upsert.value?.mode === "update" },
			},
			span: 12,
			hidden: Upsert.value?.mode !== "update",
		}),
		// 编辑时显示且只读
		() => ({
			label: t("AppSecret"),
			prop: "appSecret",
			component: {
				name: "el-input",
				props: { disabled: Upsert.value?.mode === "update" },
			},
			span: 12,
			hidden: Upsert.value?.mode !== "update",
		}),
		{
			label: t("联系人"),
			prop: "contactName",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("联系电话"),
			prop: "contactPhone",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			rules: [{ validator: phoneValidator, trigger: "blur" }],
		},
		{
			label: t("联系邮箱"),
			prop: "contactEmail",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
			rules: [{ validator: emailValidator, trigger: "blur" }],
		},
		{
			label: t("地址"),
			prop: "address",
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
			label: t("状态"),
			prop: "status",
			value: 1,
			component: {
				name: "el-select",
				props: { clearable: true },
				options: statusOptions,
			},
			span: 12,
			required: true,
		},
	],
});

// cl-table
const Table = useTable({
	columns: [
		{ type: "selection" },
		{ label: t("租户名称"), prop: "name", minWidth: 120 },
		{ label: t("租户标识"), prop: "tenantCode", minWidth: 120 },
		{ label: t("域名"), prop: "domain", minWidth: 140 },
		{ label: t("联系人"), prop: "contactName", minWidth: 100 },
		{ label: t("联系电话"), prop: "contactPhone", minWidth: 120 },
		{ label: t("状态"), prop: "status", minWidth: 80, dict: statusOptions, dictColor: true },
		{
			label: t("创建时间"),
			prop: "createTime",
			minWidth: 170,
			sortable: "desc",
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
		service: service.base.sys.tenant,
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
