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
			<div class="stats">
				<span v-for="item in statItems" :key="item.label" class="stat-chip">
					{{ item.label }}: {{ item.value }}
				</span>
			</div>
			<cl-search-key :placeholder="$t('搜索场景、配置、错误')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<el-button text type="primary" @click="showPayload(scope.row)">{{ $t('查看') }}</el-button>
					<el-button v-if="canCancel(scope.row)" text type="danger" @click="cancelTask(scope.row)">{{ $t('取消') }}</el-button>
					<el-button v-if="canRetry(scope.row)" text type="warning" @click="retryTask(scope.row)">{{ $t('重试') }}</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>

	<el-drawer v-model="submitter.visible" :title="$t('提交 AI 任务')" size="520px">
		<el-form label-position="top">
			<el-form-item :label="$t('任务类型')">
				<cl-select v-model="submitter.taskType" :options="taskTypeOptions" />
			</el-form-item>
			<el-form-item :label="$t('场景')">
				<el-input v-model="submitter.scenario" />
			</el-form-item>
			<el-form-item :label="$t('调用配置编码')">
				<el-input v-model="submitter.profileCode" clearable />
			</el-form-item>
			<el-form-item :label="$t('请求 JSON')">
				<el-input v-model="submitter.payload" type="textarea" :rows="10" />
			</el-form-item>
			<el-button type="primary" @click="submitTask">{{ $t('提交') }}</el-button>
		</el-form>
	</el-drawer>

	<el-drawer v-model="viewer.visible" :title="$t('任务详情')" size="640px">
		<el-tabs>
			<el-tab-pane :label="$t('请求')">
				<pre>{{ formatJson(viewer.row?.requestPayload) }}</pre>
			</el-tab-pane>
			<el-tab-pane :label="$t('结果')">
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
							<el-button text type="primary" @click="copyText(item.value)">{{ $t('复制') }}</el-button>
							<el-button v-if="item.url" text type="primary" @click="openUrl(item.url)">{{ $t('打开') }}</el-button>
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

import { computed, onMounted, reactive } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const aiService = service.ai as any;
const taskService = {
	page: (data: any) => aiService.runtime.model.taskPage(data),
	list: (data: any) => aiService.runtime.model.taskList(data),
	info: (data: any) => aiService.runtime.model.taskInfo(data),
	stats: (data: any) => aiService.runtime.model.taskStats(data)
};

const statusOptions = [
	{ label: t('等待中'), value: 'pending' },
	{ label: t('运行中'), value: 'running' },
	{ label: t('成功'), value: 'success' },
	{ label: t('失败'), value: 'failed' },
	{ label: t('已取消'), value: 'cancelled' }
];
const taskTypeOptions = [
	{ label: t('对话'), value: 'chat' },
	{ label: t('向量'), value: 'embedding' },
	{ label: t('图片'), value: 'image' },
	{ label: t('重排'), value: 'rerank' },
	{ label: t('音频'), value: 'audio' },
	{ label: t('视频'), value: 'video' }
];

const stats = reactive({
	statusCounts: {} as Record<string, number>,
	recentErrors: [] as string[]
});
const submitter = reactive({
	visible: false,
	taskType: 'chat',
	scenario: 'default',
	profileCode: '',
	payload: '{\n  "messages": [\n    { "role": "user", "content": "你好" }\n  ],\n  "options": { "max_tokens": 512 }\n}'
});
const viewer = reactive({
	visible: false,
	row: null as any
});

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
		{ label: t('类型'), prop: 'taskType', minWidth: 100, formatter: ({ taskType }: any) => optionLabel(taskTypeOptions, taskType) },
		{ label: t('场景'), prop: 'scenario', minWidth: 120 },
		{ label: t('配置'), prop: 'profileCode', minWidth: 140 },
		{ label: t('状态'), prop: 'status', minWidth: 110, formatter: ({ status }: any) => optionLabel(statusOptions, status) },
		{ label: t('进度'), prop: 'progress', minWidth: 90 },
		{ label: t('重试'), prop: 'retryCount', minWidth: 80 },
		{ label: t('错误信息'), prop: 'errorMessage', minWidth: 220, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', width: 220, buttons: ['slot-op'] }
	]
});

const Crud = useCrud(
	{
		service: taskService
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
	const res = await taskService.stats({});
	stats.statusCounts = res?.statusCounts || {};
	stats.recentErrors = res?.recentErrors || [];
}

function openSubmit() {
	submitter.visible = true;
}

async function submitTask() {
	try {
		const payload = JSON.parse(submitter.payload || '{}');
		await aiService.runtime.model.submitTask({
			taskType: submitter.taskType,
			scenario: submitter.scenario || 'default',
			profileCode: submitter.profileCode || undefined,
			payload
		});
		ElMessage.success(t('提交成功'));
		submitter.visible = false;
		Crud.value?.refresh();
		loadStats();
	} catch (err: any) {
		ElMessage.error(err.message || t('提交失败'));
	}
}

async function cancelTask(row: any) {
	await ElMessageBox.confirm(t('确认取消该任务？'), t('提示'), { type: 'warning' });
	await aiService.runtime.model.cancelTask({ id: row.id });
	ElMessage.success(t('取消成功'));
	Crud.value?.refresh();
	loadStats();
}

async function retryTask(row: any) {
	await aiService.runtime.model.retryTask({ id: row.id });
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

function optionLabel(options: { label: string; value: string }[], value: string) {
	return options.find(item => item.value === value)?.label || value || '-';
}

function extractImageItems(value: any): { src: string; value: string; url?: string }[] {
	const items = findImageData(value);
	return items
		.map(item => {
			const url = item?.url || item?.image_url || item?.imageUrl;
			const b64 = item?.b64_json || item?.b64Json || item?.base64;
			if (url) {
				return { src: url, value: url, url };
			}
			if (b64) {
				const src = String(b64).startsWith('data:image') ? String(b64) : `data:image/png;base64,${b64}`;
				return { src, value: String(b64) };
			}
			return null;
		})
		.filter(Boolean) as { src: string; value: string; url?: string }[];
}

function findImageData(value: any): any[] {
	if (!value) {
		return [];
	}
	if (typeof value === 'string') {
		try {
			return findImageData(JSON.parse(value));
		} catch {
			return [];
		}
	}
	if (Array.isArray(value)) {
		return value;
	}
	if (Array.isArray(value.data)) {
		return value.data;
	}
	if (value.raw) {
		const rawItems = findImageData(value.raw);
		if (rawItems.length) {
			return rawItems;
		}
	}
	if (value.result) {
		return findImageData(value.result);
	}
	if (Array.isArray(value.images)) {
		return value.images;
	}
	return [];
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
