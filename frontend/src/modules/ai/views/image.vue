<template>
	<div class="ai-image-workbench">
		<!-- 左侧：参数与提示词配置面板组件 -->
		<image-generator-panel
			:form="form"
			:loading="loading"
			:selected-profile="selectedProfile"
			:selected-profile-summary="selectedProfileSummary"
			:profile-options="profileOptions"
			:provider-kind-tag="providerKindTag"
			:provider-kind="providerKind"
			:show-bailian-negative-prompt="showBailianNegativePrompt"
			:show-watermark-option="showWatermarkOption"
			:available-size-options="availableSizeOptions"
			:allow-custom-size="allowCustomSize"
			:active-limits="activeLimits"
			:size-hint="sizeHint"
			:provider-hint="providerHint"
			:capability-tags="capabilityTags"
			:is-ernie-irag="isErnieIrag"
			@generate="generate"
			@submit-task="submitTask"
			@reset-options="resetOptions"
			@clear-result="clearResult"
		/>

		<!-- 引用资产（IP 资产库）：选中即组装预览；draft 仅本人可试生成（接口按矩阵过滤） -->
		<section class="asset-ref-card">
			<header class="asset-ref-head">
				<span class="asset-ref-title">{{ $t('引用资产') }}</span>
				<el-button
					v-if="hasAssetRefs"
					link
					size="small"
					type="primary"
					:loading="loading.generate"
					@click="previewComposer"
				>
					{{ $t('预览组装') }}
				</el-button>
			</header>
			<div class="asset-ref-grid">
				<el-select
					v-model="assetRefs.characterId"
					:placeholder="$t('角色（可空）')"
					clearable
					filterable
					size="small"
					@change="onAssetRefChange"
				>
					<el-option v-for="a in assetCharacterOptions" :key="a.id" :label="assetLabel(a)" :value="a.id" />
				</el-select>
				<el-select
					v-model="assetRefs.sceneId"
					:placeholder="$t('场景（可空）')"
					clearable
					filterable
					size="small"
					@change="previewComposer"
				>
					<el-option v-for="a in assetSceneOptions" :key="a.id" :label="assetLabel(a)" :value="a.id" />
				</el-select>
				<el-select
					v-model="assetRefs.styleId"
					:placeholder="$t('风格（可空）')"
					clearable
					filterable
					size="small"
					@change="previewComposer"
				>
					<el-option v-for="a in assetStyleOptions" :key="a.id" :label="assetLabel(a)" :value="a.id" />
				</el-select>
			</div>
			<div v-if="assetVariableKeys.length" class="asset-vars">
				<el-input
					v-for="key in assetVariableKeys"
					:key="key"
					v-model="assetVariables[key]"
					:placeholder="key"
					size="small"
					class="var-input"
				/>
			</div>
			<composer-preview v-if="composerPreview" :result="composerPreview" class="asset-preview" />
		</section>

		<!-- 右侧：生成结果画廊与调试区 -->
		<aside class="result">
			<!-- 顶部状态与统计条 -->
			<header class="result__head">
				<div class="result-title-group">
					<div class="title-row">
						<el-icon class="gallery-icon"><picture-icon /></el-icon>
						<span class="title-text">{{ $t('生成画廊') }}</span>
					</div>
					<div v-if="resultMeta.length" class="meta-row">
						<el-tag
							v-for="(meta, idx) in resultMeta"
							:key="idx"
							size="small"
							effect="plain"
							class="meta-badge"
						>
							{{ meta }}
						</el-tag>
					</div>
				</div>

				<div class="result-head-actions">
					<el-tag v-if="imageItems.length" type="success" effect="dark" round>
						{{ $t('已生成') }} {{ imageItems.length }} {{ $t('张') }}
					</el-tag>
					<el-button
						v-if="imageItems.length"
						link
						size="small"
						type="primary"
						@click="copyAllImageUrls"
					>
						<el-icon class="mr-2"><document-copy /></el-icon>
						{{ $t('复制全部链接') }}
					</el-button>
				</div>
			</header>

			<!-- 核心画廊展示组件 -->
			<image-gallery
				:task-submitted="taskSubmitted"
				:loading="loading.generate"
				:items="imageItems"
				:preview-urls="previewUrls"
				:count="form.n || 1"
				:size="form.size"
				@use-as-reference="useAsReference"
				@fill-sample="fillSamplePrompt"
			/>

			<!-- 底部折叠信息与报文审计组件 -->
			<ai-payload-inspector
				:result="result"
				:last-payload="lastPayload"
			/>
		</aside>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-image'
});

import { onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { Picture as PictureIcon, DocumentCopy } from '@element-plus/icons-vue';
import { useImageWorkbench } from '../composables/use-image-workbench';
import ImageGeneratorPanel from '../components/image-generator-panel.vue';
import ImageGallery from '../components/image-gallery.vue';
import AiPayloadInspector from '../components/ai-payload-inspector.vue';
import { ComposerPreview } from '/$/asset';

const { t } = useI18n();

const {
	form,
	result,
	lastPayload,
	loading,
	selectedProfile,
	selectedProfileSummary,
	profileOptions,
	providerKind,
	showBailianNegativePrompt,
	showWatermarkOption,
	availableSizeOptions,
	allowCustomSize,
	activeLimits,
	sizeHint,
	providerKindTag,
	providerHint,
	capabilityTags,
	imageItems,
	previewUrls,
	taskSubmitted,
	resultMeta,
	isErnieIrag,
	generate,
	submitTask,
	resetOptions,
	clearResult,
	// 资产引用（IP 资产库）
	assetRefs,
	assetVariables,
	assetVariableKeys,
	composerPreview,
	assetCharacterOptions,
	assetSceneOptions,
	assetStyleOptions,
	hasAssetRefs,
	loadAssetOptions,
	onAssetRefChange,
	previewComposer
} = useImageWorkbench();

onMounted(() => {
	loadAssetOptions();
});

const assetLabel = (a: { name: string; code: string }) => `${a.name} (${a.code})`;

function useAsReference(src: string) {
	form.image = src;
	ElMessage.success(t('已设置为参考底图'));
}

async function copyAllImageUrls() {
	if (!imageItems.value.length) return;
	const urls = imageItems.value.map(item => item.src).join('\n');
	try {
		await navigator.clipboard.writeText(urls);
		ElMessage.success(t('已复制全部图片链接到剪贴板'));
	} catch {
		ElMessage.warning(t('复制失败'));
	}
}

const SAMPLE_PROMPTS = [
	'赛博朋克风格的未来城市雨夜，霓虹灯倒影在湿润的沥青路面，飞行汽车穿梭在摩天大楼之间，高细节，虚幻引擎5渲染，8k分辨率，电影质感构图',
	'水墨画风格的江南水乡，乌篷船在晨雾弥漫的小河中缓缓前行，白墙黛瓦，两岸垂柳依依，留白意境，大师级笔触'
];

function fillSamplePrompt() {
	const random = SAMPLE_PROMPTS[Math.floor(Math.random() * SAMPLE_PROMPTS.length)];
	form.prompt = random;
	ElMessage.success(t('已填入灵感提示词'));
}
</script>

<style lang="scss" scoped>
.ai-image-workbench {
	display: grid;
	grid-template-columns: minmax(420px, 460px) minmax(0, 1fr);
	gap: 14px;
	height: calc(100vh - 110px);
	min-height: 680px;
	box-sizing: border-box;

	.result {
		display: flex;
		flex-direction: column;
		min-height: 0;
		height: 100%;
		background: var(--el-bg-color);
		border: 1px solid var(--el-border-color-light);
		border-radius: 8px;
		box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
		overflow: hidden;

		&__head {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 12px 18px;
			background: var(--el-fill-color-blank);
			border-bottom: 1px solid var(--el-border-color-lighter);
			flex-shrink: 0;

			.result-title-group {
				display: flex;
				align-items: center;
				gap: 12px;

				.title-row {
					display: flex;
					align-items: center;
					gap: 6px;

					.gallery-icon {
						font-size: 18px;
						color: var(--el-color-primary);
					}

					.title-text {
						font-size: 15px;
						font-weight: 650;
						color: var(--el-text-color-primary);
					}
				}

				.meta-row {
					display: flex;
					gap: 6px;
				}
			}

			.result-head-actions {
				display: flex;
				align-items: center;
				gap: 10px;
			}
		}
	}
}

@media (max-width: 992px) {
	.ai-image-workbench {
		grid-template-columns: 1fr;
		height: auto;
	}
}

.asset-ref-card {
	margin-top: 12px;
	padding: 12px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	display: flex;
	flex-direction: column;
	gap: 8px;
}
.asset-ref-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
}
.asset-ref-title {
	font-size: 13px;
	font-weight: 500;
}
.asset-ref-grid {
	display: grid;
	grid-template-columns: repeat(3, 1fr);
	gap: 8px;
}
.asset-vars {
	display: flex;
	gap: 8px;
	flex-wrap: wrap;
}
.var-input {
	width: 140px;
}
.asset-preview {
	max-height: 320px;
	overflow: auto;
}
</style>
