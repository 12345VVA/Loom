<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-filter :label="$t('范围')">
				<cl-select :options="scopeOptions" prop="scopeType" :width="130" />
			</cl-filter>
			<cl-filter :label="$t('模式')">
				<cl-select :options="modeOptions" prop="mode" :width="130" />
			</cl-filter>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-toggle="{ scope }">
					<el-button text type="primary" @click="toggleRule(scope.row)">
						{{ scope.row.status ? $t('停用') : $t('启用') }}
					</el-button>
				</template>
			</cl-table>
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
	name: 'ai-governance-rule'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const aiService = service.ai as any;

const scopeOptions = [
	{ label: t('全局'), value: 'global' },
	{ label: t('用户'), value: 'user' },
	{ label: 'Profile', value: 'profile' }
];
const periodOptions = [
	{ label: t('分钟'), value: 'minute' },
	{ label: t('天'), value: 'day' },
	{ label: t('月'), value: 'month' }
];
const modeOptions = [
	{ label: t('拦截'), value: 'enforce' },
	{ label: t('观察'), value: 'observe' }
];

const Upsert = useUpsert({
	dialog: { width: '860px' },
	props: { labelWidth: '150px' },
	items: [
		{ label: t('编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{ label: t('范围'), prop: 'scopeType', value: 'global', required: true, component: { name: 'cl-select', props: { options: scopeOptions } } },
		{
			label: t('用户'),
			prop: 'userId',
			component: {
				name: 'cl-select-table',
				props: {
					service: service.base.sys.user,
					multiple: false,
					dict: { text: 'fullName' },
					columns: [
						{ label: t('用户名'), prop: 'username', minWidth: 140 },
						{ label: t('姓名'), prop: 'fullName', minWidth: 140 }
					]
				}
			}
		},
		{
			label: 'Profile',
			prop: 'profileId',
			component: {
				name: 'cl-select-table',
				props: {
					service: service.ai.profile,
					multiple: false,
					dict: { text: 'name' },
					columns: [
						{ label: t('编码'), prop: 'code', minWidth: 140 },
						{ label: t('名称'), prop: 'name', minWidth: 140 },
						{ label: t('模型'), prop: 'modelName', minWidth: 140 }
					]
				}
			}
		},
		{ label: t('周期'), prop: 'period', value: 'day', component: { name: 'cl-select', props: { options: periodOptions } } },
		{ label: t('请求上限'), prop: 'maxRequests', component: { name: 'el-input-number', props: { min: 0, 'controls-position': 'right' } } },
		{ label: 'Token 上限', prop: 'maxTokens', component: { name: 'el-input-number', props: { min: 0, 'controls-position': 'right' } } },
		{ label: '成本上限(微美元)', prop: 'maxCostMicroUsd', component: { name: 'el-input-number', props: { min: 0, 'controls-position': 'right' } } },
		{ label: t('并发上限'), prop: 'maxConcurrent', component: { name: 'el-input-number', props: { min: 0, 'controls-position': 'right' } } },
		{ label: t('模式'), prop: 'mode', value: 'enforce', component: { name: 'cl-select', props: { options: modeOptions } } },
		{ label: t('通知'), prop: 'notifyEnabled', value: true, component: { name: 'el-switch' } },
		{ label: t('启用'), prop: 'status', value: true, component: { name: 'el-switch' } },
		{ label: t('排序'), prop: 'orderNum', value: 0, component: { name: 'el-input-number' } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('编码'), prop: 'code', minWidth: 150 },
		{ label: t('名称'), prop: 'name', minWidth: 150 },
		{ label: t('范围'), prop: 'scopeType', minWidth: 100, formatter: ({ scopeType }: any) => optionLabel(scopeOptions, scopeType) },
		{ label: t('用户'), prop: 'username', minWidth: 130 },
		{ label: 'Profile', prop: 'profileName', minWidth: 150 },
		{ label: t('周期'), prop: 'period', minWidth: 90, formatter: ({ period }: any) => optionLabel(periodOptions, period) },
		{ label: t('请求'), prop: 'maxRequests', minWidth: 90 },
		{ label: 'Tokens', prop: 'maxTokens', minWidth: 100 },
		{ label: 'Cost(μUSD)', prop: 'maxCostMicroUsd', minWidth: 120 },
		{ label: t('并发'), prop: 'maxConcurrent', minWidth: 90 },
		{ label: t('模式'), prop: 'mode', minWidth: 100, formatter: ({ mode }: any) => optionLabel(modeOptions, mode) },
		{ label: t('启用'), prop: 'status', width: 90 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', width: 260, buttons: ['edit', 'delete', 'slot-toggle'] }
	]
});

const Crud = useCrud(
	{
		service: aiService.governanceRule
	},
	app => {
		app.refresh();
	}
);

async function toggleRule(row: any) {
	await aiService.governanceRule.toggle({ id: row.id });
	ElMessage.success(t('操作成功'));
	Crud.value?.refresh();
}

function optionLabel(options: { label: string; value: string }[], value: string) {
	return options.find(item => item.value === value)?.label || value || '-';
}
</script>
