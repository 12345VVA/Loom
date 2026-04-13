<template>
	<cl-crud ref="Crud">
		<cl-row>
			<!-- 刷新按钮 -->
			<cl-refresh-btn />

			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索姓名、账号、IP、设备标识')" />
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
	name: "sys-login-log",
});

import { useCrud, useTable, useUpsert } from "@cool-vue/crud";
import { useCool } from "/@/cool";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";

const { service } = useCool();
const { t } = useI18n();
const loginLogService = service.base?.sys?.login_log;

const loginTypeDict = [
	{ label: "密码登录", value: "password", type: "success" },
	{ label: "退出登录", value: "logout", type: "info" },
	{ label: "短信登录", value: "sms", type: "warning" },
	{ label: "验证码登录", value: "captcha", type: "warning" },
];

const statusDict = [
	{ label: "成功", value: 1, type: "success" },
	{ label: "失败", value: 0, type: "danger" },
];

const riskHitDict = [
	{ label: "未命中", value: 0, type: "success" },
	{ label: "已命中", value: 1, type: "danger" },
];

function getDictLabel(dict: { label: string; value: string | number }[], value: any) {
	return dict.find((e) => e.value === value)?.label || (value ?? "-");
}

function formatText(value: any, fallback = "-") {
	return value === null || value === undefined || value === "" ? fallback : value;
}

function getOs(userAgent?: string) {
	const ua = (userAgent || "").toLowerCase();

	if (!ua) return "未知系统";
	if (ua.includes("windows")) return "Windows";
	if (ua.includes("mac os")) return "macOS";
	if (ua.includes("iphone") || ua.includes("ipad") || ua.includes("ios")) return "iOS";
	if (ua.includes("android")) return "Android";
	if (ua.includes("linux")) return "Linux";

	return "未知系统";
}

function getBrowser(userAgent?: string) {
	const ua = userAgent || "";

	if (!ua) return "未知浏览器";

	const rules = [
		{ name: "Edge", regex: /Edg\/([\d.]+)/i },
		{ name: "Chrome", regex: /Chrome\/([\d.]+)/i },
		{ name: "Firefox", regex: /Firefox\/([\d.]+)/i },
		{ name: "Safari", regex: /Version\/([\d.]+).*Safari/i },
	];

	for (const item of rules) {
		const match = ua.match(item.regex);

		if (match) {
			return `${item.name} ${match[1]}`;
		}
	}

	return "未知浏览器";
}

function getClientText(row: any) {
	if (row.clientType) {
		return row.clientType;
	}

	const ua = row.userAgent || "";
	const os = getOs(ua);
	const browser = getBrowser(ua);

	return `${os} / ${browser}`;
}

function getReasonText(row: any) {
	if (row.status === 1) {
		return "无";
	}

	return formatText(row.reason);
}

// cl-upsert
const Upsert = useUpsert({
	items: [
		{
			label: t("用户ID"),
			prop: "userId",
			component: { name: "el-input-number", props: { min: 1, controlsPosition: "right" } },
		},
		{
			label: t("登录方式"),
			prop: "loginType",
			component: {
				name: "el-select",
				props: { clearable: true },
				options: loginTypeDict,
			},
			span: 12,
			required: true,
		},
		{
			label: t("登录账号"),
			prop: "account",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("登录状态"),
			prop: "status",
			component: {
				name: "el-select",
				props: { clearable: true },
				options: statusDict,
			},
			span: 12,
			required: true,
		},
		{
			label: t("IP"),
			prop: "ip",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("是否命中风控"),
			prop: "riskHit",
			component: {
				name: "el-select",
				props: { clearable: true },
				options: riskHitDict,
			},
			span: 12,
			required: true,
		},
		{
			label: t("失败原因"),
			prop: "reason",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("客户端类型"),
			prop: "clientType",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("选择设备标识"),
			prop: "deviceId",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("来源系统"),
			prop: "sourceSystem",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
		{
			label: t("用户代理"),
			prop: "userAgent",
			component: { name: "el-input", props: { clearable: true } },
			span: 12,
		},
	],
});

// cl-table
const Table = useTable({
	columns: [
		{ label: t("#"), type: "index" },
		{ label: t("姓名"), prop: "name", minWidth: 120, formatter: ({ name }: any) => formatText(name) },
		{ label: t("登录账号"), prop: "account", minWidth: 120, formatter: ({ account }: any) => formatText(account) },
		{
			label: t("登录方式"),
			prop: "loginType",
			minWidth: 120,
			dict: loginTypeDict,
			dictColor: true,
			formatter: ({ loginType }: any) => getDictLabel(loginTypeDict, loginType),
		},
		{
			label: t("登录状态"),
			prop: "status",
			minWidth: 110,
			dict: statusDict,
			dictColor: true,
			formatter: ({ status }: any) => getDictLabel(statusDict, status),
		},
		{ label: t("IP"), prop: "ip", minWidth: 130, formatter: ({ ip }: any) => formatText(ip) },
		{
			label: t("风控结果"),
			prop: "riskHit",
			minWidth: 110,
			dict: riskHitDict,
			dictColor: true,
			formatter: ({ riskHit }: any) => getDictLabel(riskHitDict, riskHit),
		},
		{
			label: t("失败原因"),
			prop: "reason",
			minWidth: 140,
			showOverflowTooltip: true,
			formatter: (row: any) => getReasonText(row),
		},
		{
			label: t("终端信息"),
			prop: "clientType",
			minWidth: 180,
			showOverflowTooltip: true,
			formatter: (row: any) => getClientText(row),
		},
		{
			label: t("设备标识"),
			prop: "deviceId",
			minWidth: 140,
			showOverflowTooltip: true,
			formatter: ({ deviceId }: any) => formatText(deviceId),
		},
		{
			label: t("来源系统"),
			prop: "sourceSystem",
			minWidth: 120,
			formatter: ({ sourceSystem }: any) => formatText(sourceSystem, "管理后台"),
		},
		{
			label: t("用户代理"),
			prop: "userAgent",
			minWidth: 260,
			showOverflowTooltip: true,
			formatter: ({ userAgent }: any) => formatText(userAgent),
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
	],
});

// cl-crud
const Crud = useCrud(
	{
		service: loginLogService,
	},
	(app) => {
		if (!loginLogService) {
			ElMessage.error("登录日志服务未注册，请检查 EPS/service 命名");
			return;
		}

		app.refresh();
	},
);

// 刷新
function refresh(params?: any) {
	Crud.value?.refresh(params);
}
</script>
