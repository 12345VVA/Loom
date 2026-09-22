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
			<stat-chips :items="statItems" />
			<cl-search-key :placeholder="$t('搜索场景、状态、Request ID、错误')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #column-requestOptions="{ scope }">
					<el-button
						v-if="scope.row.requestOptions || scope.row.request_options"
						link
						type="primary"
						size="small"
						@click="viewOptions(scope.row)"
					>
						{{ $t('查看') }}
					</el-button>
					<span v-else style="color: var(--el-text-color-placeholder)">-</span>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<el-dialog
			v-model="dialogVisible"
			:title="$t('高级调用参数 (request_options)')"
			width="650px"
			destroy-on-close
		>
			<div class="options-dialog-content">
				<pre class="json-viewer">{{ currentOptionsText }}</pre>
			</div>
			<template #footer>
				<el-button @click="copyOptions">{{ $t('复制') }}</el-button>
				<el-button type="primary" @click="dialogVisible = false">{{ $t('关闭') }}</el-button>
			</template>
		</el-dialog>
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-log'
});

import { computed, reactive, ref } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import StatChips from '../components/stat-chips.vue';

const { service } = useCool();
const { t } = useI18n();

const dialogVisible = ref(false);
const currentOptionsText = ref('');

function viewOptions(row: any) {
	const raw = row.requestOptions || row.request_options || '';
	try {
		const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
		currentOptionsText.value = JSON.stringify(parsed, null, 2);
	} catch {
		currentOptionsText.value = String(raw);
	}
	dialogVisible.value = true;
}

async function copyOptions() {
	if (!currentOptionsText.value) return;
	await navigator.clipboard.writeText(currentOptionsText.value);
	ElMessage.success(t('已复制'));
}

const stats = reactive({
	total: 0,
	success: 0,
	error: 0,
	successRate: 0,
	avgLatencyMs: 0,
	totalTokens: 0
});

const statItems = computed(() => [
	{ label: t('调用'), value: stats.total },
	{ label: t('成功'), value: stats.success },
	{ label: t('错误'), value: stats.error },
	{ label: t('成功率'), value: `${(stats.successRate * 100).toFixed(2)}%` },
	{ label: t('平均延迟'), value: `${stats.avgLatencyMs}ms` },
	{ label: 'Tokens', value: stats.totalTokens }
]);

const statusOptions = [
	{ label: t('成功'), value: 'success', type: 'success' },
	{ label: t('错误'), value: 'error', type: 'danger' },
	{ label: t('未支持'), value: 'unsupported', type: 'info' }
];

const modelTypeOptions = [
	{ label: t('对话'), value: 'chat', type: 'primary' },
	{ label: t('向量'), value: 'embedding', type: 'success' },
	{ label: t('图片'), value: 'image', type: 'warning' },
	{ label: t('音频'), value: 'audio', type: 'danger' },
	{ label: t('视频'), value: 'video', type: 'info' },
	{ label: t('重排'), value: 'rerank', type: 'success' }
];

const Table = useTable({
	columns: [
		{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
		{ label: t('模型'), prop: 'modelName', minWidth: 150 },
		{ label: t('调用配置'), prop: 'profileName', minWidth: 150 },
		{ label: t('用户'), prop: 'username', minWidth: 130 },
		{ label: t('场景'), prop: 'scenario', minWidth: 120 },
		{
			label: t('类型'),
			prop: 'modelType',
			minWidth: 100,
			dict: modelTypeOptions,
			dictColor: true
		},
		{
			label: t('状态'),
			prop: 'status',
			minWidth: 110,
			dict: statusOptions,
			dictColor: true
		},
		{ label: t('延迟(ms)'), prop: 'latencyMs', minWidth: 110 },
		{ label: t('高级参数'), prop: 'requestOptions', minWidth: 100 },
		{ label: 'Prompt Tokens', prop: 'promptTokens', minWidth: 130 },
		{ label: 'Completion Tokens', prop: 'completionTokens', minWidth: 160 },
		{ label: 'Total Tokens', prop: 'totalTokens', minWidth: 120 },
		{ label: 'Cost(USD)', prop: 'costUsd', minWidth: 110 },
		{ label: 'Request ID', prop: 'requestId', minWidth: 180, showOverflowTooltip: true },
		{ label: t('错误信息'), prop: 'errorMessage', minWidth: 240, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 }
	]
});

const Crud = useCrud(
	{
		service: service.ai.log
	},
	app => {
		app.refresh();
		loadStats();
	}
);

async function loadStats() {
	const res = await service.ai.log.stats({});
	Object.assign(stats, res || {});
}
</script>

<style lang="scss" scoped>
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

.options-dialog-content {
	max-height: 480px;
	overflow-y: auto;
}

.json-viewer {
	margin: 0;
	padding: 12px;
	background-color: var(--el-fill-color-light);
	border-radius: 4px;
	font-family: monospace;
	font-size: 13px;
	line-height: 1.5;
	white-space: pre-wrap;
	word-break: break-all;
}
</style>
