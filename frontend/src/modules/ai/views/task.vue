<template>
	<cl-crud ref="Crud">
		<cl-row class="toolbar-row">
			<cl-refresh-btn />
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" :width="140" clearable />
			</cl-filter>
			<cl-filter :label="$t('任务类型')">
				<cl-select :options="taskTypeOptions" prop="taskType" :width="140" clearable />
			</cl-filter>
			<cl-multi-delete-btn />
			<cl-flex1 />
			<stat-chips :items="statItems" />
			<cl-search-key :placeholder="$t('搜索场景、配置、错误')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<el-button
						v-permission="service.ai.task.permission?.info"
						text
						type="primary"
						@click="showPayload(scope.row)"
					>
						{{ $t('查看') }}
					</el-button>
					<el-button
						v-if="canCancel(scope.row)"
						v-permission="service.ai.task.permission?.cancel"
						text
						type="danger"
						@click="cancelTask(scope.row)"
					>
						{{ $t('取消') }}
					</el-button>
					<el-button
						v-if="canRetry(scope.row)"
						v-permission="service.ai.task.permission?.retry"
						text
						type="warning"
						@click="retryTask(scope.row)"
					>
						{{ $t('重试') }}
					</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<el-drawer v-model="viewer.visible" :title="$t('任务详情')" size="640px">
			<el-tabs>
				<el-tab-pane :label="$t('请求')">
					<pre>{{ formatJson(viewer.row?.requestPayload) }}</pre>
				</el-tab-pane>
				<el-tab-pane :label="$t('结果')">
					<el-descriptions v-if="viewer.row" class="task-meta" border :column="2">
						<el-descriptions-item label="Task ID">{{
							viewer.row.id || '-'
						}}</el-descriptions-item>
						<el-descriptions-item :label="$t('状态')">{{
							statusOptions.find((item) => item.value === viewer.row.status)?.label ||
							viewer.row.status ||
							'-'
						}}</el-descriptions-item>
						<el-descriptions-item :label="$t('配置')">{{
							viewer.row.profileCode || '-'
						}}</el-descriptions-item>
						<el-descriptions-item :label="$t('进度')">{{
							viewer.row.progress ?? '-'
						}}</el-descriptions-item>
					</el-descriptions>
					<div v-if="taskImageItems.length" class="image-results">
						<div v-for="(item, index) in taskImageItems" :key="index" class="image-result">
							<el-image
								class="image-result__preview"
								:src="item.src"
								fit="contain"
								:preview-src-list="taskPreviewUrls"
								:initial-index="index"
								preview-teleported
							/>
							<div class="image-result__actions">
								<el-button text type="primary" @click="copyText(item.value)">
									{{ $t('复制') }}
								</el-button>
								<el-button
									v-if="item.url"
									text
									type="primary"
									@click="openUrl(item.url)"
								>
									{{ $t('打开') }}
								</el-button>
							</div>
						</div>
					</div>
					<pre>{{ formatJson(viewer.row?.resultPayload) }}</pre>
				</el-tab-pane>
				<el-tab-pane :label="$t('错误')">
					<pre>{{ viewer.row?.errorMessage || '-' }}</pre>
				</el-tab-pane>
			</el-tabs>
		</el-drawer>
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-task'
});

import { computed, reactive } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { extractImageItems } from '../utils/image-utils';
import StatChips from '../components/stat-chips.vue';

const { service } = useCool();
const { t } = useI18n();

const statusOptions = [
	{ label: t('等待中'), value: 'pending', type: 'info' },
	{ label: t('运行中'), value: 'running', type: 'primary' },
	{ label: t('成功'), value: 'success', type: 'success' },
	{ label: t('失败'), value: 'failed', type: 'danger' },
	{ label: t('已取消'), value: 'cancelled', type: 'warning' }
];
const taskTypeOptions = [
	{ label: t('对话'), value: 'chat', type: 'primary' },
	{ label: t('向量'), value: 'embedding', type: 'success' },
	{ label: t('图片'), value: 'image', type: 'warning' },
	{ label: t('重排'), value: 'rerank', type: 'success' },
	{ label: t('音频'), value: 'audio', type: 'danger' },
	{ label: t('视频'), value: 'video', type: 'info' }
];

const stats = reactive({
	statusCounts: {} as Record<string, number>,
	recentErrors: [] as string[]
});
const viewer = reactive({
	visible: false,
	row: null as any
});

const statItems = computed(() =>
	statusOptions.map((item) => ({
		label: item.label,
		value: stats.statusCounts[item.value] || 0
	}))
);
const taskImageItems = computed(() => {
	if (viewer.row?.taskType !== 'image') {
		return [];
	}
	return extractImageItems(viewer.row?.resultPayload);
});
const taskPreviewUrls = computed(() => taskImageItems.value.map((item) => item.src));

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{
			label: t('类型'),
			prop: 'taskType',
			minWidth: 100,
			dict: taskTypeOptions,
			dictColor: true
		},
		{ label: t('场景'), prop: 'scenario', minWidth: 120 },
		{ label: t('配置'), prop: 'profileCode', minWidth: 140 },
		{
			label: t('状态'),
			prop: 'status',
			minWidth: 110,
			dict: statusOptions,
			dictColor: true
		},
		{ label: t('进度'), prop: 'progress', minWidth: 90 },
		{ label: t('重试'), prop: 'retryCount', minWidth: 80 },
		{ label: t('错误信息'), prop: 'errorMessage', minWidth: 220, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170, component: { name: 'cl-date-text' } },
		{ type: 'op', width: 240, fixed: 'right', buttons: ['slot-op', 'delete'] }
	],
	contextMenu: ['refresh', 'check', 'delete']
});

const Crud = useCrud(
	{
		service: service.ai.task
	},
	(app) => {
		app.refresh();
		loadStats();
	}
);

async function loadStats() {
	const res = await service.ai.task.stats({});
	stats.statusCounts = res?.statusCounts || {};
	stats.recentErrors = res?.recentErrors || [];
}

function showPayload(row: any) {
	viewer.row = row;
	viewer.visible = true;
}

function canCancel(row: any) {
	return row.status === 'pending' || row.status === 'running';
}

function canRetry(row: any) {
	return row.status === 'failed' || row.status === 'cancelled';
}

async function cancelTask(row: any) {
	await ElMessageBox.confirm(t('确定要取消该任务吗？'), t('提示'), { type: 'warning' });
	try {
		await service.ai.task.cancel({ id: row.id });
		ElMessage.success(t('任务已取消'));
		Crud.value?.refresh();
		loadStats();
	} catch (err: any) {
		ElMessage.error(err.message || t('取消失败'));
	}
}

async function retryTask(row: any) {
	await ElMessageBox.confirm(t('确定要重试该任务吗？'), t('提示'), { type: 'info' });
	try {
		await service.ai.task.retry({ id: row.id });
		ElMessage.success(t('任务已重新提交'));
		Crud.value?.refresh();
		loadStats();
	} catch (err: any) {
		ElMessage.error(err.message || t('重试失败'));
	}
}

function formatJson(val: any) {
	if (!val) return '-';
	if (typeof val === 'string') {
		try {
			return JSON.stringify(JSON.parse(val), null, 2);
		} catch {
			return val;
		}
	}
	return JSON.stringify(val, null, 2);
}

function copyText(val: string) {
	if (!val) return;
	navigator.clipboard.writeText(val);
	ElMessage.success(t('已复制'));
}

function openUrl(url: string) {
	if (!url) return;
	window.open(url, '_blank');
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

.task-meta {
	margin-bottom: 16px;
}

.image-results {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	margin-bottom: 16px;
}

.image-result {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 6px;

	&__preview {
		width: 120px;
		height: 120px;
		border: 1px solid var(--el-border-color-lighter);
		border-radius: 6px;
		background: var(--el-fill-color-light);
	}

	&__actions {
		display: flex;
		gap: 4px;
	}
}

pre {
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
