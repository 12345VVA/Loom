<template>
	<cl-crud ref="Crud">
		<cl-row class="toolbar-row">
			<cl-refresh-btn />
			<cl-filter :label="$t('事件')">
				<cl-select :options="eventOptions" prop="eventType" :width="130" />
			</cl-filter>
			<cl-filter :label="$t('指标')">
				<cl-select :options="metricOptions" prop="metric" :width="130" />
			</cl-filter>
			<cl-flex1 />
			<div class="stats">
				<span v-for="item in statItems" :key="item.label" class="stat-chip"
					>{{ item.label }}: {{ item.value }}</span
				>
			</div>
			<cl-search-key :placeholder="$t('搜索事件、指标、消息')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-governance-event'
});

import { computed, onMounted, reactive } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const aiService = service.ai as any;

const eventOptions = [
	{ label: t('放行'), value: 'allowed' },
	{ label: t('拦截'), value: 'blocked' },
	{ label: t('告警'), value: 'warn' }
];
const metricOptions = [
	{ label: t('请求'), value: 'request' },
	{ label: t('并发'), value: 'concurrent' },
	{ label: 'Token', value: 'token' },
	{ label: t('成本'), value: 'cost' }
];
const stats = reactive({
	total: 0,
	byType: {} as Record<string, number>,
	byMetric: {} as Record<string, number>
});

const statItems = computed(() => [
	{ label: t('总数'), value: stats.total || 0 },
	{ label: t('拦截'), value: stats.byType.blocked || 0 },
	{ label: t('告警'), value: stats.byType.warn || 0 },
	{ label: t('请求'), value: stats.byMetric.request || 0 },
	{ label: t('成本'), value: stats.byMetric.cost || 0 }
]);

const Table = useTable({
	columns: [
		{ label: t('规则'), prop: 'ruleName', minWidth: 150 },
		{ label: t('用户'), prop: 'username', minWidth: 130 },
		{ label: 'Profile', prop: 'profileName', minWidth: 150 },
		{ label: t('模型'), prop: 'modelName', minWidth: 150 },
		{
			label: t('事件'),
			prop: 'eventType',
			minWidth: 100,
			formatter: ({ eventType }: any) => optionLabel(eventOptions, eventType)
		},
		{
			label: t('指标'),
			prop: 'metric',
			minWidth: 100,
			formatter: ({ metric }: any) => optionLabel(metricOptions, metric)
		},
		{ label: t('当前值'), prop: 'currentValue', minWidth: 100 },
		{ label: t('限制值'), prop: 'limitValue', minWidth: 100 },
		{ label: t('已通知'), prop: 'notified', minWidth: 90 },
		{ label: t('消息'), prop: 'message', minWidth: 260, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 }
	]
});

const Crud = useCrud(
	{
		service: aiService.governanceEvent
	},
	app => {
		app.refresh();
		loadStats();
	}
);

onMounted(loadStats);

async function loadStats() {
	const res = await aiService.governanceEvent.stats({ days: 14 });
	stats.total = res?.total || 0;
	stats.byType = res?.byType || {};
	stats.byMetric = res?.byMetric || {};
}

function optionLabel(options: { label: string; value: string }[], value: string) {
	return options.find(item => item.value === value)?.label || value || '-';
}
</script>

<style lang="scss" scoped>
.stats {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	align-items: center;
}

.stat-chip {
	box-sizing: border-box;
	height: 36px;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	padding: 0 12px;
	border: 1px solid var(--el-color-primary-light-5);
	border-radius: 6px;
	background: var(--el-fill-color-blank);
	color: var(--el-color-primary);
	font-size: 14px;
	line-height: 1;
	white-space: nowrap;
}

.toolbar-row {
	align-items: center;
}
</style>
