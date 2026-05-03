<template>
	<cl-crud ref="Crud">
		<cl-row class="toolbar-row">
			<cl-refresh-btn />
			<cl-filter :label="$t('类型')">
				<cl-select :options="assetTypeOptions" prop="assetType" :width="120" />
			</cl-filter>
			<cl-filter :label="$t('来源')">
				<cl-select :options="sourceTypeOptions" prop="sourceType" :width="120" />
			</cl-filter>
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" :width="130" />
			</cl-filter>
			<el-upload :show-file-list="false" :http-request="uploadAsset">
				<el-button type="primary">{{ $t('上传资源') }}</el-button>
			</el-upload>
			<cl-flex1 />
			<div class="media-stats">
				<span v-for="item in statItems" :key="item.label" class="stat-chip">
					{{ item.label }}: {{ item.value }}
				</span>
			</div>
			<cl-search-key :placeholder="$t('搜索文件名、提示词、链接')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #column-preview="{ scope }">
					<div class="preview-cell" @click="openPreview(scope.row)">
						<el-image v-if="scope.row.assetType === 'image' && scope.row.storageUrl" :src="assetUrl(scope.row.storageUrl)" fit="cover" />
						<el-icon v-else class="preview-icon"><component :is="iconFor(scope.row.assetType)" /></el-icon>
					</div>
				</template>

				<template #column-status="{ scope }">
					<el-tag :type="statusType(scope.row.status)" effect="plain">{{ scope.row.status }}</el-tag>
				</template>

				<template #column-sizeBytes="{ scope }">
					{{ formatSize(scope.row.sizeBytes) }}
				</template>

				<template #slot-op="{ scope }">
					<el-button text type="primary" @click="openPreview(scope.row)">{{ $t('预览') }}</el-button>
					<el-button v-if="scope.row.storageUrl" text type="primary" @click="copyText(assetUrl(scope.row.storageUrl))">{{ $t('复制') }}</el-button>
					<el-button v-if="scope.row.storageUrl" text type="primary" @click="openUrl(assetUrl(scope.row.storageUrl))">{{ $t('打开') }}</el-button>
					<el-button text type="danger" @click="deleteAsset(scope.row)">{{ $t('删除') }}</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>

	<el-drawer v-model="viewer.visible" :title="$t('资源预览')" size="680px">
		<div v-if="viewer.row" class="asset-preview">
			<el-image
				v-if="viewer.row.assetType === 'image' && viewer.row.storageUrl"
				class="asset-preview__image"
				:src="assetUrl(viewer.row.storageUrl)"
				fit="contain"
				:preview-src-list="[assetUrl(viewer.row.storageUrl)]"
				preview-teleported
			/>
			<video v-else-if="viewer.row.assetType === 'video' && viewer.row.storageUrl" class="asset-preview__media" :src="assetUrl(viewer.row.storageUrl)" controls />
			<audio v-else-if="viewer.row.assetType === 'audio' && viewer.row.storageUrl" class="asset-preview__audio" :src="assetUrl(viewer.row.storageUrl)" controls />
			<el-empty v-else :description="$t('暂无可预览内容')" />

			<el-descriptions border :column="1">
				<el-descriptions-item :label="$t('文件名')">{{ viewer.row.fileName || '-' }}</el-descriptions-item>
				<el-descriptions-item label="MD5">{{ viewer.row.md5 || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('资源链接')">{{ viewer.row.storageUrl || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('原始链接')">{{ viewer.row.originalUrl || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('提示词')">{{ viewer.row.prompt || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('错误')">{{ viewer.row.errorMessage || '-' }}</el-descriptions-item>
			</el-descriptions>
		</div>
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'media-asset'
});

import { computed, onMounted, reactive } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Document, Headset, Picture, VideoCamera } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { config } from '/@/config';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const mediaService = (service as any).media.asset;

const assetTypeOptions = [
	{ label: t('图片'), value: 'image' },
	{ label: t('视频'), value: 'video' },
	{ label: t('音频'), value: 'audio' },
	{ label: t('文件'), value: 'file' }
];
const sourceTypeOptions = [
	{ label: t('AI 任务'), value: 'ai_task' },
	{ label: t('同步生成'), value: 'ai_sync' },
	{ label: t('上传'), value: 'upload' }
];
const statusOptions = [
	{ label: t('等待中'), value: 'pending' },
	{ label: t('转存中'), value: 'transferring' },
	{ label: t('成功'), value: 'success' },
	{ label: t('失败'), value: 'failed' },
	{ label: t('已删除'), value: 'deleted' }
];

const stats = reactive({
	typeCounts: {} as Record<string, number>,
	statusCounts: {} as Record<string, number>,
	sourceCounts: {} as Record<string, number>
});
const viewer = reactive({
	visible: false,
	row: null as any
});

const statItems = computed(() => [
	{ label: t('图片'), value: stats.typeCounts.image || 0 },
	{ label: t('视频'), value: stats.typeCounts.video || 0 },
	{ label: t('音频'), value: stats.typeCounts.audio || 0 },
	{ label: t('文件'), value: stats.typeCounts.file || 0 },
	{ label: t('失败'), value: stats.statusCounts.failed || 0 }
]);

const Table = useTable({
	columns: [
		{ label: t('预览'), prop: 'preview', width: 92 },
		{ label: t('文件名'), prop: 'fileName', minWidth: 190, showOverflowTooltip: true },
		{ label: t('类型'), prop: 'assetType', minWidth: 90, formatter: ({ assetType }: any) => optionLabel(assetTypeOptions, assetType) },
		{ label: t('来源'), prop: 'sourceType', minWidth: 110, formatter: ({ sourceType }: any) => optionLabel(sourceTypeOptions, sourceType) },
		{ label: t('状态'), prop: 'status', minWidth: 120, formatter: ({ status }: any) => optionLabel(statusOptions, status) },
		{ label: t('大小'), prop: 'sizeBytes', minWidth: 100 },
		{ label: 'MD5', prop: 'md5', minWidth: 220, showOverflowTooltip: true },
		{ label: t('提示词'), prop: 'prompt', minWidth: 220, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', width: 250, buttons: ['slot-op'] }
	]
});

const Crud = useCrud(
	{
		service: mediaService
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
	const res = await mediaService.stats({});
	stats.typeCounts = res?.typeCounts || {};
	stats.statusCounts = res?.statusCounts || {};
	stats.sourceCounts = res?.sourceCounts || {};
}

async function uploadAsset(options: any) {
	const form = new FormData();
	form.append('file', options.file);
	try {
		await mediaService.request({
			url: '/upload',
			method: 'POST',
			data: form
		});
		ElMessage.success(t('上传成功'));
		Crud.value?.refresh();
		loadStats();
		options.onSuccess?.({});
	} catch (err: any) {
		ElMessage.error(err.message || t('上传失败'));
		options.onError?.(err);
	}
}

async function deleteAsset(row: any) {
	await ElMessageBox.confirm(t('确认删除该资源？'), t('提示'), { type: 'warning' });
	const res = await mediaService.delete({ ids: [row.id] });
	if (res?.failedIds?.length) {
		ElMessage.warning(t('部分资源删除失败'));
	} else {
		ElMessage.success(t('删除成功'));
	}
	Crud.value?.refresh();
	loadStats();
}

function openPreview(row: any) {
	viewer.row = row;
	viewer.visible = true;
}

async function copyText(value: string) {
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制'));
}

function openUrl(url: string) {
	window.open(url, '_blank');
}

function assetUrl(url?: string) {
	if (!url) {
		return '';
	}
	if (/^(https?:)?\/\//.test(url) || url.startsWith('data:')) {
		return url;
	}
	if (url.startsWith('/uploads/')) {
		return `${config.baseUrl}${url}`;
	}
	return url;
}

function formatSize(value: number) {
	const size = Number(value || 0);
	if (size < 1024) {
		return `${size} B`;
	}
	if (size < 1024 * 1024) {
		return `${(size / 1024).toFixed(1)} KB`;
	}
	return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function statusType(status: string) {
	if (status === 'success') {
		return 'success';
	}
	if (status === 'failed') {
		return 'danger';
	}
	if (status === 'transferring') {
		return 'warning';
	}
	return 'info';
}

function optionLabel(options: { label: string; value: string }[], value: string) {
	return options.find(item => item.value === value)?.label || value || '-';
}

function iconFor(type: string) {
	if (type === 'image') {
		return Picture;
	}
	if (type === 'video') {
		return VideoCamera;
	}
	if (type === 'audio') {
		return Headset;
	}
	return Document;
}
</script>

<style lang="scss" scoped>
.media-stats {
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

.preview-cell {
	width: 56px;
	height: 56px;
	display: grid;
	place-items: center;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	overflow: hidden;
	cursor: pointer;
	background: var(--el-fill-color-light);

	.el-image {
		width: 100%;
		height: 100%;
	}
}

.preview-icon {
	font-size: 24px;
	color: var(--el-text-color-secondary);
}

.asset-preview {
	display: grid;
	gap: 16px;
}

.asset-preview__image,
.asset-preview__media {
	width: 100%;
	max-height: 420px;
	background: var(--el-fill-color-light);
	border-radius: 6px;
}

.asset-preview__audio {
	width: 100%;
}
</style>
