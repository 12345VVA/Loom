<template>
	<cl-crud ref="Crud">
		<cl-row class="toolbar-row">
			<cl-refresh-btn />
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" :width="140" />
			</cl-filter>
			<cl-filter :label="$t('任务类型')">
				<cl-select :options="taskTypeOptions" prop="taskType" :width="140" />
			</cl-filter>
			<el-button type="primary" @click="openSubmit">{{ $t('提交任务') }}</el-button>
			<cl-flex1 />
			<stat-chips :items="statItems" />
			<cl-search-key :placeholder="$t('搜索场景、配置、错误')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<el-button text type="primary" @click="showPayload(scope.row)">{{
						$t('查看')
					}}</el-button>
					<el-button
						v-if="canCancel(scope.row)"
						text
						type="danger"
						@click="cancelTask(scope.row)"
						>{{ $t('取消') }}</el-button
					>
					<el-button
						v-if="canRetry(scope.row)"
						text
						type="warning"
						@click="retryTask(scope.row)"
						>{{ $t('重试') }}</el-button
					>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>

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
						statusOptions.find(item => item.value === viewer.row.status)?.label ||
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
							<el-button text type="primary" @click="copyText(item.value)">{{
								$t('复制')
							}}</el-button>
							<el-button
								v-if="item.url"
								text
								type="primary"
								@click="openUrl(item.url)"
								>{{ $t('打开') }}</el-button
							>
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
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-task'
});

import { computed, reactive } from 'vue';
import { useCrud, useForm, useTable } from '@cool-vue/crud';
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
const Form = useForm();

const statItems = computed(() =>
	statusOptions.map(item => ({
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
const taskPreviewUrls = computed(() => taskImageItems.value.map(item => item.src));

const Table = useTable({
	columns: [
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
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', width: 220, buttons: ['slot-op'] }
	]
});

const Crud = useCrud(
	{
		service: service.ai.task
	},
	app => {
		app.refresh();
		loadStats();
	}
);

async function loadStats() {
	const res = await service.ai.task.stats({});
	stats.statusCounts = res?.statusCounts || {};
	stats.recentErrors = res?.recentErrors || [];
}

function openSubmit() {
	Form.value?.open({
		title: t('提交 AI 任务'),
		width: '600px',
		form: {
			taskType: 'chat',
			scenario: 'default',
			profileCode: '',
			payload:
				'{\n  "messages": [\n    { "role": "user", "content": "你好" }\n  ],\n  "options": { "max_tokens": 512 }\n}'
		},
		items: [
			{
				label: t('任务类型'),
				prop: 'taskType',
				required: true,
				component: { name: 'cl-select', props: { options: taskTypeOptions } }
			},
			{ label: t('场景'), prop: 'scenario' },
			{ label: t('调用配置编码'), prop: 'profileCode' },
			{
				label: t('请求 JSON'),
				prop: 'payload',
				component: {
					name: 'cl-editor',
					props: { name: 'cl-editor-codemirror', height: 300 }
				}
			}
		],
		on: {
			async submit(data, { close, done }) {
				try {
					const payload = JSON.parse(data.payload || '{}');
					await service.ai.task.submit({
						taskType: data.taskType,
						scenario: data.scenario || 'default',
						profileCode: data.profileCode || undefined,
						payload
					});
					ElMessage.success(t('提交成功'));
					close();
					Crud.value?.refresh();
					loadStats();
				} catch (err: any) {
					ElMessage.error(err.message || t('提交失败'));
					done();
				}
			}
		}
	});
}

async function cancelTask(row: any) {
	await ElMessageBox.confirm(t('确认取消该任务？'), t('提示'), { type: 'warning' });
	await service.ai.task.cancel({ id: row.id });
	ElMessage.success(t('取消成功'));
	Crud.value?.refresh();
	loadStats();
}

async function retryTask(row: any) {
	await service.ai.task.retry({ id: row.id });
	ElMessage.success(t('已重新提交'));
	Crud.value?.refresh();
	loadStats();
}

function showPayload(row: any) {
	viewer.row = row;
	viewer.visible = true;
}

function canCancel(row: any) {
	return ['pending', 'running'].includes(row.status);
}

function canRetry(row: any) {
	return ['failed', 'cancelled'].includes(row.status);
}

function formatJson(value?: string) {
	if (!value) {
		return '-';
	}
	try {
		return JSON.stringify(JSON.parse(value), null, 2);
	} catch {
		return value;
	}
}

async function copyText(value: string) {
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制'));
}

function openUrl(url: string) {
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

pre {
	margin: 0;
	white-space: pre-wrap;
	word-break: break-word;
	font-size: 12px;
}

.image-results {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
	gap: 12px;
	margin-bottom: 12px;
}

.task-meta {
	margin-bottom: 12px;
}

.image-result {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-blank);

	&__preview {
		display: block;
		width: 100%;
		height: 180px;
		background: var(--el-fill-color-lighter);
	}

	&__actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 8px;
	}
}
</style>
