<template>
	<cl-crud ref="Crud">
		<cl-row class="toolbar-row">
			<cl-refresh-btn />
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" :width="130" />
			</cl-filter>
			<cl-filter :label="$t('模型类型')">
				<cl-select :options="modelTypeOptions" prop="modelType" :width="130" />
			</cl-filter>
			<cl-flex1 />
			<div class="stats">
				<span class="stat-chip">{{ $t('调用') }}: {{ stats.total }}</span>
				<span class="stat-chip">{{ $t('成功') }}: {{ stats.success }}</span>
				<span class="stat-chip">{{ $t('错误') }}: {{ stats.error }}</span>
				<span class="stat-chip">{{ $t('成功率') }}: {{ (stats.successRate * 100).toFixed(2) }}%</span>
				<span class="stat-chip">{{ $t('平均延迟') }}: {{ stats.avgLatencyMs }}ms</span>
				<span class="stat-chip">Tokens: {{ stats.totalTokens }}</span>
			</div>
			<cl-search-key :placeholder="$t('搜索场景、状态、Request ID、错误')" />
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
	name: 'ai-log'
});

import { onMounted, reactive } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const aiService = service.ai as any;
const stats = reactive({
	total: 0,
	success: 0,
	error: 0,
	successRate: 0,
	avgLatencyMs: 0,
	totalTokens: 0
});

const statusOptions = [
	{ label: t('成功'), value: 'success' },
	{ label: t('错误'), value: 'error' },
	{ label: t('未支持'), value: 'unsupported' }
];

const modelTypeOptions = [
	{ label: t('对话'), value: 'chat' },
	{ label: t('向量'), value: 'embedding' },
	{ label: t('图片'), value: 'image' },
	{ label: t('音频'), value: 'audio' },
	{ label: t('视频'), value: 'video' },
	{ label: t('重排'), value: 'rerank' }
];

const Table = useTable({
	columns: [
		{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
		{ label: t('模型'), prop: 'modelName', minWidth: 150 },
		{ label: t('调用配置'), prop: 'profileName', minWidth: 150 },
		{ label: t('场景'), prop: 'scenario', minWidth: 120 },
		{ label: t('类型'), prop: 'modelType', minWidth: 100, formatter: ({ modelType }: any) => optionLabel(modelTypeOptions, modelType) },
		{ label: t('状态'), prop: 'status', minWidth: 110, formatter: ({ status }: any) => optionLabel(statusOptions, status) },
		{ label: t('延迟(ms)'), prop: 'latencyMs', minWidth: 110 },
		{ label: 'Prompt Tokens', prop: 'promptTokens', minWidth: 130 },
		{ label: 'Completion Tokens', prop: 'completionTokens', minWidth: 160 },
		{ label: 'Total Tokens', prop: 'totalTokens', minWidth: 120 },
		{ label: 'Request ID', prop: 'requestId', minWidth: 180, showOverflowTooltip: true },
		{ label: t('错误信息'), prop: 'errorMessage', minWidth: 240, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 }
	]
});

const Crud = useCrud(
	{
		service: aiService.log
	},
	app => {
		app.refresh();
		loadStats();
	}
);

onMounted(() => {
	loadStats();
});

async function loadStats() {
	const res = await aiService.log.stats({});
	Object.assign(stats, res || {});
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

	:deep(.el-button),
	:deep(.el-input__wrapper),
	:deep(.el-select__wrapper) {
		box-sizing: border-box;
		height: 36px;
		min-height: 36px;
	}

	:deep(.el-button) {
		padding: 0 14px;
	}
}
</style>
