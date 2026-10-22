<template>
	<cl-crud ref="Crud">
		<cl-row class="toolbar-row">
			<cl-refresh-btn />
			<cl-filter :label="$t('类型')">
				<cl-select :options="assetTypeOptions" prop="asset_type" :width="120" />
			</cl-filter>
			<cl-filter :label="$t('来源')">
				<cl-select :options="sourceTypeOptions" prop="source_type" :width="120" />
			</cl-filter>
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" :width="130" />
			</cl-filter>
			<el-upload :show-file-list="false" :http-request="uploadAsset">
				<el-button type="primary">{{ $t('上传资源') }}</el-button>
			</el-upload>
			<el-button
				v-if="stats.statusCounts?.failed"
				type="warning"
				plain
				:loading="retryingAll"
				@click="retryAllFailed"
			>
				<el-icon><refresh /></el-icon>
				{{ $t('重试失败资源') }} ({{ stats.statusCounts.failed }})
			</el-button>
			<el-button
				v-if="stats.mirrorPendingCount > 0"
				type="warning"
				plain
				:loading="backfilling"
				@click="backfillMirror"
			>
				<el-icon><upload-filled /></el-icon>
				{{ $t('补镜像存量') }} ({{ stats.mirrorPendingCount }})
			</el-button>
			<el-button :loading="probing" @click="runMirrorProbe">
				<el-icon><connection /></el-icon>
				{{ $t('测试云端存储') }}
			</el-button>
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
						<el-image
							v-if="previewSrc(scope.row)"
							:src="previewSrc(scope.row)"
							fit="cover"
						/>
						<el-icon v-else class="preview-icon"
							><component :is="iconFor(scope.row.assetType)"
						/></el-icon>
					</div>
				</template>

				<template #column-status="{ scope }">
					<el-tag :type="statusType(scope.row.status)" effect="plain">{{
						scope.row.status
					}}</el-tag>
				</template>

				<template #column-mirrorTag="{ scope }">
					<el-tag
						v-if="scope.row.status === 'success'"
						:type="scope.row.remoteUrl ? 'success' : 'info'"
						effect="plain"
					>
						{{ scope.row.remoteUrl ? $t('已镜像') : $t('未镜像') }}
					</el-tag>
					<span v-else>-</span>
				</template>

				<template #column-sizeBytes="{ scope }">
					{{ formatSize(scope.row.sizeBytes) }}
				</template>

				<template #slot-op="{ scope }">
					<el-button text type="primary" @click="openPreview(scope.row)">{{
						$t('预览')
					}}</el-button>
					<el-button
						v-if="scope.row.status === 'failed'"
						text
						type="warning"
						:loading="retryingIds.has(scope.row.id)"
						@click="retryAsset(scope.row)"
					>
						{{ $t('重试转存') }}
					</el-button>
					<el-button
						v-if="scope.row.status === 'success' && !scope.row.remoteUrl"
						text
						type="primary"
						:loading="mirroringIds.has(scope.row.id)"
						@click="mirrorAsset(scope.row)"
					>
						{{ $t('镜像') }}
					</el-button>
					<el-button
						v-if="scope.row.remoteUrl"
						text
						type="primary"
						@click="openUrl(scope.row.remoteUrl)"
						>{{ $t('打开云端') }}</el-button
					>
					<el-button
						v-if="scope.row.storageUrl"
						text
						type="primary"
						@click="copyText(assetUrl(scope.row.storageUrl))"
						>{{ $t('复制') }}</el-button
					>
					<el-button
						v-if="scope.row.assetType === 'image' && scope.row.status === 'success'"
						text
						type="success"
						@click="openSetReference(scope.row)"
						>{{ $t('设为角色参考图') }}</el-button
					>
					<el-button
						v-if="scope.row.storageUrl"
						text
						type="primary"
						@click="openUrl(assetUrl(scope.row.storageUrl))"
						>{{ $t('打开') }}</el-button
					>
					<el-button text type="danger" @click="deleteAsset(scope.row)">{{
						$t('删除')
					}}</el-button>
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
			<el-alert
				v-if="viewer.row.status === 'failed'"
				type="error"
				show-icon
				:closable="false"
				class="failure-alert"
			>
				<template #title>
					<div class="failure-title">
						<span class="failure-text">{{ $t('转存失败: ') }}{{ viewer.row.errorMessage || $t('未知错误') }}</span>
						<el-button
							size="small"
							type="warning"
							:loading="retryingIds.has(viewer.row.id as number)"
							@click="retryAsset(viewer.row)"
						>
							{{ $t('立即重试转存') }}
						</el-button>
					</div>
				</template>
			</el-alert>
			<el-image
				v-if="previewSrc(viewer.row)"
				class="asset-preview__image"
				:src="previewSrc(viewer.row)"
				fit="contain"
				:preview-src-list="[previewSrc(viewer.row)]"
				preview-teleported
			/>
			<video
				v-else-if="viewer.row.assetType === 'video' && viewer.row.storageUrl"
				class="asset-preview__media"
				:src="assetUrl(viewer.row.storageUrl)"
				controls
			/>
			<audio
				v-else-if="viewer.row.assetType === 'audio' && viewer.row.storageUrl"
				class="asset-preview__audio"
				:src="assetUrl(viewer.row.storageUrl)"
				controls
			/>
			<el-empty v-else :description="$t('暂无可预览内容')" />

			<el-descriptions border :column="1">
				<el-descriptions-item :label="$t('文件名')">{{
					viewer.row.fileName || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="MD5">{{ viewer.row.md5 || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('资源链接')">{{
					viewer.row.storageUrl || '-'
				}}</el-descriptions-item>
				<el-descriptions-item :label="$t('云端镜像')">
					<div v-if="viewer.row.remoteUrl" class="remote-url">
						<span class="remote-url__text">{{ viewer.row.remoteUrl }}</span>
						<el-button text type="primary" size="small" @click="copyText(viewer.row.remoteUrl)">{{
							$t('复制')
						}}</el-button>
						<el-button text type="primary" size="small" @click="openUrl(viewer.row.remoteUrl)">{{
							$t('打开')
						}}</el-button>
					</div>
					<template v-else>
						<span>{{ viewer.row.status === 'success' ? $t('未镜像') : '-' }}</span>
						<el-button
							v-if="viewer.row.status === 'success'"
							text
							type="primary"
							size="small"
							:loading="mirroringIds.has(viewer.row.id as number)"
							@click="mirrorAsset(viewer.row)"
						>
							{{ $t('立即镜像') }}
						</el-button>
					</template>
				</el-descriptions-item>
				<el-descriptions-item :label="$t('原始链接')">{{
					viewer.row.originalUrlPreview || viewer.row.originalUrl || '-'
				}}</el-descriptions-item>
				<el-descriptions-item :label="$t('来源')">{{
					optionLabel(sourceTypeOptions, viewer.row.sourceType)
				}}</el-descriptions-item>
				<el-descriptions-item label="Provider">{{
					viewer.row.providerCode || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="Model">{{
					viewer.row.modelCode || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="Profile">{{
					viewer.row.profileCode || '-'
				}}</el-descriptions-item>
				<el-descriptions-item :label="$t('提示词')">{{
					viewer.row.prompt || '-'
				}}</el-descriptions-item>
				<el-descriptions-item :label="$t('参数')">
					<pre class="params-preview">{{ formatJson(viewer.row.paramsPayload) }}</pre>
				</el-descriptions-item>
				<el-descriptions-item :label="$t('错误')">{{
					viewer.row.errorMessage || '-'
				}}</el-descriptions-item>
			</el-descriptions>
		</div>
	</el-drawer>

	<el-dialog v-model="probe.visible" :title="$t('云端存储自检')" width="600px">
		<div v-if="probe.data" class="mirror-probe">
			<el-descriptions border :column="1" size="small">
				<el-descriptions-item :label="$t('镜像开关')">
					<el-tag :type="probe.data.config.enabled ? 'success' : 'danger'" effect="plain" size="small">
						{{ probe.data.config.enabled ? $t('已开启') : $t('未开启') }}
					</el-tag>
				</el-descriptions-item>
				<el-descriptions-item :label="$t('端点')">{{ probe.data.config.endpoint || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('桶')">{{ probe.data.config.bucket || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('传输方式')">
					{{ probe.data.config.transport === 'tos-native' ? 'TOS 原生 SDK' : 'S3 兼容 (boto3)' }}
				</el-descriptions-item>
				<el-descriptions-item label="AccessKey">{{ probe.data.config.accessKey || '-' }}</el-descriptions-item>
			</el-descriptions>
			<div class="mirror-probe__steps">
				<div v-for="(step, key) in probe.data.steps" :key="key" class="mirror-probe__step">
					<el-icon :class="step.ok ? 'is-ok' : 'is-fail'">
						<circle-check-filled v-if="step.ok" />
						<circle-close-filled v-else />
					</el-icon>
					<span class="mirror-probe__step-name">{{ stepName(String(key)) }}</span>
					<span class="mirror-probe__step-meta">{{ step.elapsedMs }}ms</span>
					<span v-if="!step.ok && step.error" class="mirror-probe__step-error">{{ step.error }}</span>
				</div>
			</div>
		</div>
	</el-dialog>

	<!-- 设为角色参考图（需求 4.3） -->
	<el-dialog v-model="setRefDialog.visible" :title="$t('设为角色参考图')" width="420px" append-to-body>
		<el-form label-width="90px">
			<el-form-item :label="$t('角色')">
				<el-select v-model="setRefDialog.characterId" filterable :placeholder="$t('仅列出可编辑资产')">
					<el-option v-for="a in setRefOptions" :key="a.id" :label="`${a.name} (${a.code})`" :value="a.id" />
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('首选')">
				<el-switch v-model="setRefDialog.role" active-value="primary" :active-text="$t('设为首选')" />
			</el-form-item>
		</el-form>
		<template #footer>
			<el-button @click="setRefDialog.visible = false">{{ $t('取消') }}</el-button>
			<el-button type="primary" @click="confirmSetReference">{{ $t('确定') }}</el-button>
		</template>
	</el-dialog>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'media-asset'
});

import { computed, onMounted, reactive, ref } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { UploadAjaxError } from 'element-plus/es/components/upload/src/ajax';
import type { UploadRequestOptions } from 'element-plus';
import {
	CircleCloseFilled,
	CircleCheckFilled,
	Connection,
	Document,
	Headset,
	Picture,
	Refresh,
	UploadFilled,
	VideoCamera
} from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { useAssetUrl } from '../composables/use-asset-url';
import { useUserStore } from '/$/base/store/user';

interface AssetCharacterOption {
	id: number;
	code: string;
	name: string;
	status: string;
	createdBy?: number | null;
}

/** request 拦截器 reject 的错误形态（Promise.reject({ message })，非 Error 实例） */
interface ApiError {
	message?: string;
}

/** 云端存储自检弹窗数据（后端 probe_mirror()：config 脱敏摘要 + 三步探针） */
interface MirrorProbeStep {
	ok: boolean;
	/** cleanup 跳过场景后端不返回该键 */
	elapsedMs?: number;
	error?: string;
}

interface MirrorProbeConfig {
	enabled: boolean;
	endpoint?: string | null;
	bucket?: string | null;
	transport?: string;
	accessKey?: string;
}

interface MirrorProbeResult {
	config: MirrorProbeConfig;
	steps: Record<string, MirrorProbeStep>;
}

const { service } = useCool();
const { t } = useI18n();
const mediaService = service.media.asset;

// ---- 设为角色参考图（IP 资产库，需求 4.3 产物回流）----
const setRefDialog = reactive({ visible: false, mediaId: 0, characterId: undefined as number | undefined, role: undefined as string | undefined });
const setRefOptions = ref<AssetCharacterOption[]>([]);

async function openSetReference(row: { id: number }) {
	setRefDialog.mediaId = row.id;
	setRefDialog.characterId = undefined;
	setRefDialog.role = undefined;
	setRefDialog.visible = true;
	try {
		const rows = await service.asset.character.list({});
		const uid = useUserStore().info?.id;
		// 仅本人可编辑行（draft 本人 + published；archived 锁死）
		setRefOptions.value = (rows || []).filter(
			(r: { id?: number; status?: string; createdBy?: number | null }) =>
				r.id != null && (r.status === 'published' || (r.status === 'draft' && r.createdBy === uid))
		) as unknown as AssetCharacterOption[];
	} catch {
		setRefOptions.value = [];
	}
}

async function confirmSetReference() {
	if (!setRefDialog.characterId) {
		ElMessage.warning(t('请选择角色'));
		return;
	}
	await service.asset.character.addReference({
		id: setRefDialog.characterId,
		mediaId: setRefDialog.mediaId,
		role: setRefDialog.role || undefined
	});
	ElMessage.success(t('已设为角色参考图'));
	setRefDialog.visible = false;
}

const retryingIds = reactive(new Set<number>());
const retryingAll = ref(false);
const mirroringIds = reactive(new Set<number>());
const backfilling = ref(false);
const probing = ref(false);
const probe = reactive({
	visible: false,
	data: null as MirrorProbeResult | null
});

const assetTypeOptions = [
	{ label: t('图片'), value: 'image' },
	{ label: t('视频'), value: 'video' },
	{ label: t('音频'), value: 'audio' },
	{ label: t('文件'), value: 'file' }
];
const sourceTypeOptions = [
	{ label: t('AI 任务'), value: 'ai_task' },
	{ label: t('同步生成'), value: 'ai_sync' },
	{ label: t('工作流'), value: 'workflow' },
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
	sourceCounts: {} as Record<string, number>,
	mirroredCount: 0,
	mirrorPendingCount: 0
});
const viewer = reactive({
	visible: false,
	row: null as Eps.asset | null
});

const statItems = computed(() => [
	{ label: t('图片'), value: stats.typeCounts.image || 0 },
	{ label: t('视频'), value: stats.typeCounts.video || 0 },
	{ label: t('音频'), value: stats.typeCounts.audio || 0 },
	{ label: t('文件'), value: stats.typeCounts.file || 0 },
	{ label: t('失败'), value: stats.statusCounts.failed || 0 },
	{ label: t('已镜像'), value: stats.mirroredCount || 0 }
]);

const Table = useTable<Eps.asset>({
	columns: [
		{ label: t('预览'), prop: 'preview', width: 92 },
		{ label: t('文件名'), prop: 'fileName', minWidth: 190, showOverflowTooltip: true },
		{
			label: t('类型'),
			prop: 'assetType',
			minWidth: 90,
			formatter: ({ assetType }) => optionLabel(assetTypeOptions, assetType)
		},
		{
			label: t('来源'),
			prop: 'sourceType',
			minWidth: 110,
			formatter: ({ sourceType }) => optionLabel(sourceTypeOptions, sourceType)
		},
		{
			label: t('状态'),
			prop: 'status',
			minWidth: 120,
			formatter: ({ status }) => optionLabel(statusOptions, status)
		},
		{
			label: t('云端'),
			prop: 'mirrorTag',
			minWidth: 90
		},
		{
			label: t('来源实例'),
			prop: 'workflowInstanceId',
			minWidth: 100,
			formatter: ({ workflowInstanceId }) => workflowInstanceId ?? '-'
		},
		{ label: t('大小'), prop: 'sizeBytes', minWidth: 100 },
		{ label: 'MD5', prop: 'md5', minWidth: 220, showOverflowTooltip: true },
		{ label: t('提示词'), prop: 'prompt', minWidth: 220, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', width: 350, buttons: ['slot-op'] }
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

// 专用下载令牌 + 资产地址拼接：抽为 composable 供产物视图复用
const { assetUrl, ensureDownloadToken } = useAssetUrl();

onMounted(() => {
	loadStats();
	ensureDownloadToken();
});

async function loadStats() {
	const res = await mediaService.stats({});
	stats.typeCounts = res?.typeCounts || {};
	stats.statusCounts = res?.statusCounts || {};
	stats.sourceCounts = res?.sourceCounts || {};
	stats.mirroredCount = res?.mirroredCount || 0;
	stats.mirrorPendingCount = res?.mirrorPendingCount || 0;
}

async function mirrorAsset(row: Eps.asset) {
	if (!row?.id) return;
	mirroringIds.add(row.id);
	try {
		const res = await mediaService.request({
			url: '/mirror',
			method: 'POST',
			data: { id: row.id }
		});
		if (res?.remoteUrl) {
			row.remoteUrl = res.remoteUrl;
			if (viewer.visible && viewer.row && viewer.row.id === row.id) {
				viewer.row.remoteUrl = res.remoteUrl;
			}
			ElMessage.success(t('镜像成功'));
			loadStats();
		} else {
			ElMessage.warning(res?.reason || t('镜像跳过'));
		}
	} catch (err) {
		ElMessage.error((err as ApiError).message || t('镜像失败'));
	} finally {
		mirroringIds.delete(row.id);
	}
}

async function backfillMirror() {
	try {
		await ElMessageBox.confirm(
			t('确定为存量资产派发镜像任务（成功转存且未镜像的资源，异步执行）？'),
			t('提示'),
			{ type: 'warning' }
		);
	} catch {
		return;
	}

	backfilling.value = true;
	try {
		const res = await mediaService.request({
			url: '/mirrorBackfill',
			method: 'POST',
			data: { limit: 100 }
		});
		if (res?.message) {
			ElMessage.warning(res.message);
		} else {
			ElMessage.success(t('已派发 {n} 个镜像任务', { n: res?.dispatched ?? 0 }));
		}
	} catch (err) {
		ElMessage.error((err as ApiError).message || t('批量派发失败'));
	} finally {
		backfilling.value = false;
	}
}

async function runMirrorProbe() {
	probing.value = true;
	try {
		const res = await mediaService.request({
			url: '/mirrorProbe',
			method: 'GET'
		});
		probe.data = res;
		probe.visible = true;
	} catch (err) {
		ElMessage.error((err as ApiError).message || t('自检请求失败'));
	} finally {
		probing.value = false;
	}
}

function stepName(key: string) {
	const names: Record<string, string> = {
		upload: t('上传探针对象'),
		anonymousGet: t('匿名公网读取'),
		cleanup: t('清理探针')
	};
	return names[key] || key;
}

async function uploadAsset(options: UploadRequestOptions) {
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
	} catch (err) {
		ElMessage.error((err as ApiError).message || t('上传失败'));
		options.onError?.(err as UploadAjaxError);
	}
}

async function deleteAsset(row: Eps.asset) {
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

async function retryAsset(row: Eps.asset) {
	if (!row?.id) return;
	retryingIds.add(row.id);
	try {
		const res = await mediaService.retry({ id: row.id });
		ElMessage.success(res?.message || t('重试转存成功'));
		if (viewer.visible && viewer.row && viewer.row.id === row.id) {
			viewer.row.status = 'success';
			viewer.row.storageUrl = res.storage_url || viewer.row.storageUrl;
			viewer.row.errorMessage = undefined;
		}
		Crud.value?.refresh();
		loadStats();
	} catch (err) {
		ElMessage.error((err as ApiError).message || t('重试转存失败'));
	} finally {
		retryingIds.delete(row.id);
	}
}

async function retryAllFailed() {
	try {
		await ElMessageBox.confirm(
			t('确定重新尝试转存所有失败的资源（限24小时内）？'),
			t('提示'),
			{ type: 'warning' }
		);
	} catch {
		return;
	}

	retryingAll.value = true;
	try {
		const res = await mediaService.retryFailed({ limit: 100, window_hours: 24 });
		ElMessage.success(
			t('重试完成：成功 {s} 项，失败 {f} 项', {
				s: res?.succeeded ?? 0,
				f: res?.failed ?? 0
			})
		);
		Crud.value?.refresh();
		loadStats();
	} catch (err) {
		ElMessage.error((err as ApiError).message || t('批量重试失败'));
	} finally {
		retryingAll.value = false;
	}
}

function openPreview(row: Eps.asset) {
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

function previewSrc(row?: Eps.asset | null) {
	if (!row || row.assetType !== 'image') {
		return '';
	}
	if (row.storageUrl) {
		return assetUrl(row.storageUrl);
	}
	if (typeof row.originalUrl === 'string' && row.originalUrl.startsWith('data:image')) {
		return row.originalUrl;
	}
	return '';
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

function optionLabel(options: { label: string; value: string }[], value?: string) {
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

.params-preview {
	margin: 0;
	white-space: pre-wrap;
	word-break: break-word;
	font-size: 12px;
}

.remote-url {
	display: flex;
	align-items: center;
	gap: 4px;
	min-width: 0;
}

.remote-url__text {
	flex: 1;
	min-width: 0;
	word-break: break-all;
	color: var(--el-text-color-regular);
}

.mirror-probe {
	display: grid;
	gap: 14px;
}

.mirror-probe__steps {
	display: grid;
	gap: 8px;
}

.mirror-probe__step {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 13px;

	.is-ok {
		color: var(--el-color-success);
	}

	.is-fail {
		color: var(--el-color-danger);
	}
}

.mirror-probe__step-name {
	min-width: 96px;
}

.mirror-probe__step-meta {
	color: var(--el-text-color-secondary);
	font-size: 12px;
}

.mirror-probe__step-error {
	color: var(--el-color-danger);
	font-size: 12px;
	word-break: break-all;
}

.failure-alert {
	margin-bottom: 4px;

	:deep(.el-alert__content) {
		width: 100%;
	}
}

.failure-title {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	width: 100%;
}

.failure-text {
	flex: 1;
	word-break: break-all;
	font-size: 13px;
	line-height: 1.4;
}
</style>
