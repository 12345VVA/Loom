<template>
	<!--
		工作流实例产物抽屉：图片网格 + 文本/JSON 卡片。
		数据来自成功终态落地的 workflow_artifact（与执行日志/快照解耦）。
	-->
	<el-drawer
		:model-value="visible"
		:size="size"
		:title="$t('实例产物')"
		destroy-on-close
		@update:model-value="(v: boolean) => emit('update:visible', v)"
		@close="emit('close')"
	>
		<div v-loading="loading" style="padding: 10px">
			<template v-if="items.length > 0">
				<div v-if="imageItems.length > 0" class="artifact-preview-list">
					<div v-for="(item, index) in imageItems" :key="item.id" class="artifact-preview-item">
						<el-image
							class="artifact-preview-image"
							:src="item.src"
							fit="contain"
							:preview-src-list="previewUrls"
							:initial-index="index"
							preview-teleported
						/>
						<div class="artifact-preview-meta">
							<span class="artifact-field-key">{{ item.fieldKey }}</span>
							<div class="artifact-preview-actions">
								<el-button text type="primary" @click="copyValue(item.copyText)">{{
									$t('复制')
								}}</el-button>
							</div>
						</div>
					</div>
				</div>

				<el-card
					v-for="item in textItems"
					:key="item.id"
					shadow="hover"
					style="margin-bottom: 10px"
				>
					<template #header>
						<div class="artifact-card-header">
							<div style="display: flex; align-items: center; gap: 8px">
								<strong>{{ item.fieldKey }}</strong>
								<el-tag v-if="item.fieldPath" size="small" type="info">{{
									item.fieldPath
								}}</el-tag>
							</div>
							<el-tag size="small" :type="item.assetType === 'json' ? 'warning' : 'info'">
								{{ item.assetType }}
							</el-tag>
						</div>
					</template>
					<div class="artifact-text-body">
						<div class="section-header">
							<el-button
								link
								type="primary"
								:icon="CopyDocument"
								@click="copyValue(item.copyText)"
								>{{ $t('复制') }}</el-button
							>
						</div>
						<pre>{{ item.display }}</pre>
					</div>
				</el-card>
			</template>
			<el-empty v-else-if="!loading" :description="$t('该实例暂无产物')" />
		</div>
	</el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { CopyDocument } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { copyToClipboard, formatJson } from '../utils';
import { useAssetUrl } from '/$/media/composables/use-asset-url';

defineOptions({ name: 'workflow-artifact-drawer' });

const props = defineProps<{
	visible: boolean;
	instanceId?: number;
	size?: string;
}>();

const emit = defineEmits<{
	(e: 'update:visible', v: boolean): void;
	(e: 'close'): void;
}>();

const { service } = useCool();
const { t } = useI18n();
const { assetUrl } = useAssetUrl();

interface ArtifactItem {
	id: number;
	fieldKey: string;
	fieldPath?: string;
	assetType: string;
	storageUrl?: string;
	originalUrl?: string;
	content?: string;
	contentRef?: string;
}

const loading = ref(false);
const items = ref<ArtifactItem[]>([]);

watch(
	() => props.visible,
	visible => {
		if (visible && props.instanceId) {
			fetchArtifacts(props.instanceId);
		}
	}
);

async function fetchArtifacts(instanceId: number) {
	loading.value = true;
	items.value = [];
	try {
		const res = await (service as any).workflow.artifact.page({
			instanceId,
			page: 1,
			size: 200
		});
		items.value = res?.items || [];
	} catch (err: any) {
		ElMessage.error(t('获取产物失败: ') + (err.message || err));
	} finally {
		loading.value = false;
	}
}

interface DisplayItem {
	id: number;
	fieldKey: string;
	fieldPath?: string;
	assetType: string;
	src: string;
	copyText: string;
	display: string;
}

function toDisplay(item: ArtifactItem): DisplayItem {
	if (item.assetType === 'image') {
		const raw = item.storageUrl || item.originalUrl || '';
		return {
			id: item.id,
			fieldKey: item.fieldKey,
			fieldPath: item.fieldPath,
			assetType: item.assetType,
			src: assetUrl(raw),
			copyText: raw,
			display: raw
		};
	}
	const raw = item.content || item.contentRef || '';
	return {
		id: item.id,
		fieldKey: item.fieldKey,
		fieldPath: item.fieldPath,
		assetType: item.assetType,
		src: '',
		copyText: raw,
		display: formatJson(raw)
	};
}

const displayItems = computed(() => items.value.map(toDisplay));
const imageItems = computed(() => displayItems.value.filter(i => i.assetType === 'image' && i.src));
const textItems = computed(() => displayItems.value.filter(i => i.assetType !== 'image'));
const previewUrls = computed(() => imageItems.value.map(i => i.src));

async function copyValue(value: string) {
	await copyToClipboard(value);
	ElMessage.success(t('已复制'));
}
</script>

<style lang="scss" scoped>
.artifact-preview-list {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
	gap: 12px;
	margin-bottom: 14px;
}

.artifact-preview-item {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-blank);
	overflow: hidden;
}

.artifact-preview-image {
	display: block;
	width: 100%;
	height: 200px;
	background: var(--el-fill-color-lighter);
}

.artifact-preview-meta {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 4px 8px;
}

.artifact-field-key {
	font-size: 12px;
	color: var(--el-text-color-secondary);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.artifact-preview-actions {
	display: flex;
	justify-content: flex-end;
}

.artifact-card-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
}

.artifact-text-body {
	.section-header {
		display: flex;
		justify-content: flex-end;
		margin-bottom: 4px;
	}

	pre {
		background-color: var(--el-fill-color-light);
		padding: 10px;
		border-radius: 4px;
		font-family: monospace;
		font-size: 12px;
		margin: 4px 0 0 0;
		overflow-x: auto;
		white-space: pre-wrap;
		word-break: break-all;
		max-height: 320px;
		overflow-y: auto;
	}
}
</style>
