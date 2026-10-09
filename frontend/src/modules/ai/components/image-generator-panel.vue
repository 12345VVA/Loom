<template>
	<section class="generator">
		<!-- 面板顶部标题 -->
		<header class="generator__head">
			<div class="head-info">
				<div class="head-title">
					<el-icon class="title-icon"><magic-stick /></el-icon>
					<h2>{{ $t('AI 生图工作台') }}</h2>
				</div>
				<span class="head-summary">{{ selectedProfileSummary }}</span>
			</div>
			<el-tag :type="providerKindTag.type" effect="plain" round class="provider-tag">
				{{ providerKindTag.label }}
			</el-tag>
		</header>

		<!-- 可滚动的内容区 -->
		<div class="generator__body">
			<!-- 顶部温馨提示条 -->
			<div v-if="showTopNotice" class="top-notice">
				<div class="top-notice__body">
					<el-icon class="notice-icon"><bell /></el-icon>
					<span class="notice-text">
						{{ $t('不同模型支持的图生图、尺寸规格和专属参数存在差异，可悬停各标题旁的小图标查看说明。') }}
					</span>
				</div>
				<el-icon class="close-icon" @click="closeTopNotice"><close /></el-icon>
			</div>

			<!-- 1. 调用配置 -->
			<div class="config-card">
				<div class="card-header">
					<span class="card-title">{{ $t('调用配置') }}</span>
				</div>
				<cl-select
					v-model="form.profileCode"
					:options="profileOptions"
					:placeholder="$t('默认图片配置')"
					clearable
					style="width: 100%"
				/>

				<div v-if="selectedProfile" class="profile-meta">
					<el-tag size="small" effect="light">{{ selectedProfile.providerName || '-' }}</el-tag>
					<el-tag size="small" type="success" effect="light">
						{{ selectedProfile.modelName || selectedProfile.modelId }}
					</el-tag>
					<el-tag size="small" type="info" effect="plain">
						{{ selectedProfile.modelType || 'image' }}
					</el-tag>
					<el-tag
						v-for="item in capabilityTags"
						:key="item"
						size="small"
						type="warning"
						effect="plain"
					>
						{{ item }}
					</el-tag>
				</div>
			</div>

			<!-- 2. 正向提示词 -->
			<div class="config-card">
				<div class="card-header space-between">
					<div class="title-with-tip">
						<span class="card-title">{{ $t('提示词 (Prompt)') }}</span>
					</div>
					<div class="header-tools">
						<el-button link type="primary" size="small" @click="fillSamplePrompt">
							<el-icon class="mr-2"><magic-stick /></el-icon>
							{{ $t('示例灵感') }}
						</el-button>
						<el-button link size="small" @click="form.prompt = ''">
							<el-icon class="mr-2"><delete /></el-icon>
							{{ $t('清空') }}
						</el-button>
					</div>
				</div>

				<div class="prompt-box">
					<el-input
						v-model="form.prompt"
						type="textarea"
						:rows="5"
						resize="none"
						class="prompt-textarea"
						:placeholder="$t('描述想要生成的画面内容、艺术风格、光影构图、色彩与细节... 支持按 Ctrl + Enter 快速生成')"
						@keydown="handlePromptKeydown"
					/>
					<div class="prompt-footer">
						<span class="shortcut-tip">{{ $t('按 Ctrl + Enter 快捷生成') }}</span>
						<span
							class="counter-tip"
							:class="{
								'is-limit':
									(isErnieIrag && form.prompt.length > 220) ||
									(activeLimits.max_prompt_length &&
										form.prompt.length > activeLimits.max_prompt_length)
							}"
						>
							{{ form.prompt.length }}
							<template v-if="isErnieIrag">/ 220</template>
							<template v-else-if="activeLimits.max_prompt_length">
								/ {{ activeLimits.max_prompt_length }}
							</template>
						</span>
					</div>
				</div>

				<!-- 超长告警 -->
				<div v-if="isErnieIrag && form.prompt.length > 220" class="field-tip warning">
					<el-icon><info-filled /></el-icon>
					<span>{{ $t('提示：当前为 ERNIE iRAG 检索增强生图，Prompt 长度超过 220 字符限额，后端将自动截断。') }}</span>
				</div>
				<div
					v-if="
						!isErnieIrag &&
						activeLimits.max_prompt_length &&
						form.prompt.length > activeLimits.max_prompt_length
					"
					class="field-tip warning"
				>
					<el-icon><info-filled /></el-icon>
					<span>
						{{ $t('提示：当前 Prompt 长度已超过模型推荐限制（最大') }}
						{{ activeLimits.max_prompt_length }} {{ $t('字符）。') }}
					</span>
				</div>

				<!-- 负向提示词 (阿里百炼等模型支持) -->
				<div v-if="showBailianNegativePrompt" class="negative-prompt-box">
					<div class="sub-title">
						<span>{{ $t('负向提示词 (Negative Prompt)') }}</span>
						<el-button link size="small" type="primary" @click="fillDefaultNegativePrompt">
							{{ $t('常用滤镜') }}
						</el-button>
					</div>
					<el-input
						v-model="form.negativePrompt"
						type="textarea"
						:rows="2"
						resize="none"
						:placeholder="$t('不想在画面中出现的元素，如：低清晰度、畸形手足、色偏、文字水印、粗糙质感')"
					/>
				</div>
			</div>

			<!-- 3. 参考图片 (图生图) -->
			<div class="config-card">
				<div class="card-header space-between">
					<div class="title-with-tip">
						<span class="card-title">{{ $t('参考图片 (图生图)') }}</span>
						<el-tooltip
							:content="$t('仅在火山方舟、阿里百炼、谷歌 Gemini 和 OpenAI 兼容等支持图生图的模型下生效。')"
							placement="top"
						>
							<el-icon class="title-tip-icon"><info-filled /></el-icon>
						</el-tooltip>
					</div>
					<el-radio-group v-model="imageInputMode" size="small">
						<el-radio-button value="upload">{{ $t('本地上传') }}</el-radio-button>
						<el-radio-button value="url">{{ $t('图片地址') }}</el-radio-button>
					</el-radio-group>
				</div>

				<div class="reference-input-area">
					<div v-if="imageInputMode === 'upload'" class="upload-wrapper">
						<cl-upload v-model="form.image" :limit="1" />
						<span v-if="!form.image" class="upload-hint">{{ $t('支持拖拽或点击上传单张参考底图') }}</span>
					</div>
					<div v-else class="url-input-wrapper">
						<el-input
							v-model="form.image"
							:placeholder="$t('请输入参考图片的公开 HTTP/HTTPS 地址')"
							clearable
						>
							<template #prefix>
								<el-icon><picture-icon /></el-icon>
							</template>
						</el-input>
						<div v-if="form.image" class="url-image-preview">
							<el-image :src="form.image" fit="cover" class="preview-thumb" />
							<el-button link type="danger" size="small" @click="form.image = ''">
								{{ $t('移除') }}
							</el-button>
						</div>
					</div>
				</div>
			</div>

			<!-- 4. 生图参数配置 -->
			<div class="config-card">
				<div class="card-header">
					<div class="title-with-tip">
						<span class="card-title">{{ $t('生图参数') }}</span>
						<el-tooltip v-if="sizeHint" :content="sizeHint" placement="top">
							<el-icon class="title-tip-icon"><info-filled /></el-icon>
						</el-tooltip>
					</div>
				</div>

				<!-- 快速比例快捷切换胶囊 -->
				<div class="aspect-ratio-selector">
					<span class="ratio-label">{{ $t('常用比例:') }}</span>
					<div class="ratio-chips">
						<button
							v-for="ratio in COMMON_RATIOS"
							:key="ratio.key"
							type="button"
							class="ratio-chip"
							:class="{ 'is-active': isRatioActive(form.size, ratio.key) }"
							@click="onSelectRatio(ratio.key)"
						>
							<span class="ratio-icon" :class="ratio.iconClass"></span>
							<span class="ratio-name">{{ ratio.label }}</span>
						</button>
					</div>
				</div>

				<!-- 规整双列参数 -->
				<div class="field-grid field-grid--compact mt-10">
					<el-form-item :label="$t('尺寸规格')">
						<el-select
							v-model="form.size"
							filterable
							:allow-create="allowCustomSize"
							default-first-option
							clearable
							style="width: 100%"
						>
							<el-option
								v-for="item in availableSizeOptions"
								:key="item.value"
								:label="item.label"
								:value="item.value"
							/>
						</el-select>
					</el-form-item>

					<el-form-item :label="$t('生成张数')">
						<el-input-number
							v-model="form.n"
							:min="1"
							:max="activeLimits.max_n || 8"
							controls-position="right"
							style="width: 100%"
						/>
					</el-form-item>

					<el-form-item v-if="providerKind !== 'poryf'" :label="$t('返回格式')">
						<cl-select
							v-model="form.responseFormat"
							:options="RESPONSE_FORMAT_OPTIONS"
							style="width: 100%"
						/>
					</el-form-item>

					<el-form-item v-if="showWatermarkOption" :label="$t('平台水印')">
						<el-switch v-model="form.watermark" active-text="开启" inactive-text="关闭" inline-prompt />
					</el-form-item>
				</div>
			</div>

			<!-- 5. 厂商专属参数 -->
			<image-provider-params
				:form="form"
				:provider-kind="providerKind"
				:provider-hint="providerHint"
				:is-ernie-irag="isErnieIrag"
			/>

			<!-- 6. 高级参数与选项 (默认收起) -->
			<div class="config-card config-card--collapse">
				<el-collapse>
					<el-collapse-item name="advanced">
						<template #title>
							<div class="collapse-title">
								<el-icon><setting /></el-icon>
								<span>{{ $t('高级参数与选项') }}</span>
								<span class="collapse-sub">{{ $t('(业务场景 / JSON 透传)') }}</span>
							</div>
						</template>
						<div class="advanced-editor">
							<div class="scenario-field mb-10">
								<div class="field-label-row">
									<span class="label-text">{{ $t('业务场景编码 (Scenario)') }}:</span>
									<el-tooltip :content="$t('未指定调用配置时按此场景路由默认模型，亦用于审计日志归类')" placement="top">
										<el-icon class="title-tip-icon"><info-filled /></el-icon>
									</el-tooltip>
								</div>
								<el-input
									v-model="form.scenario"
									:placeholder="$t('默认为 default')"
									clearable
								/>
							</div>

							<div class="advanced-tools">
								<span class="tool-note">{{ $t('可覆盖或透传专属参数（如 quality, seed, lora 等）') }}</span>
								<div class="tool-buttons">
									<el-button link size="small" type="primary" @click="formatOptionsJson">
										{{ $t('格式化') }}
									</el-button>
									<el-button link size="small" @click="$emit('reset-options')">
										{{ $t('重置') }}
									</el-button>
								</div>
							</div>
							<el-input
								v-model="form.optionsText"
								type="textarea"
								:rows="5"
								class="code-textarea"
							/>
						</div>
					</el-collapse-item>
				</el-collapse>
			</div>
		</div>

		<!-- 底部固定常驻操作栏 -->
		<footer class="generator__footer">
			<div class="footer-left">
				<el-button plain size="default" @click="$emit('clear-result')">
					<el-icon class="mr-2"><refresh /></el-icon>
					{{ $t('清空') }}
				</el-button>
			</div>
			<div class="footer-right">
				<el-button
					:loading="loading.submit"
					type="warning"
					plain
					size="default"
					@click="$emit('submit-task')"
				>
					{{ $t('异步提交任务') }}
				</el-button>
				<el-button
					:loading="loading.generate"
					type="primary"
					size="default"
					class="generate-main-btn"
					@click="$emit('generate')"
				>
					<el-icon v-if="!loading.generate" class="mr-2"><magic-stick /></el-icon>
					<span>{{ loading.generate ? $t('正在生成...') : $t('立即生成') }}</span>
				</el-button>
			</div>
		</footer>
	</section>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'image-generator-panel'
});

import { ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import {
	Bell,
	Close,
	InfoFilled,
	MagicStick,
	Delete,
	Picture as PictureIcon,
	Setting,
	Refresh
} from '@element-plus/icons-vue';
import { RESPONSE_FORMAT_OPTIONS, type ImageProviderKind } from '../utils/image-providers';
import { COMMON_RATIOS, isRatioActive, selectBestRatioSize } from '../utils/ratio-helper';
import ImageProviderParams from './image-provider-params.vue';

const { t } = useI18n();

const props = defineProps<{
	form: any;
	loading: {
		generate: boolean;
		submit: boolean;
	};
	selectedProfile: any;
	selectedProfileSummary: string;
	profileOptions: Array<{ label: string; value: string }>;
	providerKindTag: { label: string; type: any };
	providerKind: ImageProviderKind;
	showBailianNegativePrompt: boolean;
	showWatermarkOption: boolean;
	availableSizeOptions: Array<{ label: string; value: string }>;
	allowCustomSize: boolean;
	activeLimits: any;
	sizeHint: string;
	providerHint: string;
	capabilityTags: string[];
	isErnieIrag: boolean;
}>();

const emit = defineEmits<{
	(e: 'generate'): void;
	(e: 'submit-task'): void;
	(e: 'reset-options'): void;
	(e: 'clear-result'): void;
}>();

const showTopNotice = ref(localStorage.getItem('loom_ai_image_notice_closed') !== 'true');

function closeTopNotice() {
	showTopNotice.value = false;
	localStorage.setItem('loom_ai_image_notice_closed', 'true');
}

const imageInputMode = ref('upload');

watch(imageInputMode, () => {
	if (typeof props.form.image !== 'string') {
		props.form.image = '';
	}
});

function onSelectRatio(ratioKey: string) {
	const best = selectBestRatioSize(props.availableSizeOptions, ratioKey);
	if (best) {
		props.form.size = best;
	}
}

function handlePromptKeydown(e: Event | KeyboardEvent) {
	if (e instanceof KeyboardEvent && e.ctrlKey && e.key === 'Enter') {
		e.preventDefault();
		if (!props.loading.generate) {
			emit('generate');
		}
	}
}

const SAMPLE_PROMPTS = [
	'赛博朋克风格的未来城市雨夜，霓虹灯倒影在湿润的沥青路面，飞行汽车穿梭在摩天大楼之间，高细节，虚幻引擎5渲染，8k分辨率，电影质感构图',
	'水墨画风格的江南水乡，乌篷船在晨雾弥漫的小河中缓缓前行，白墙黛瓦，两岸垂柳依依，留白意境，大师级笔触',
	'微距摄影，一朵盛开的粉色樱花瓣上的清晨露珠，晶莹剔透，折射出阳光的七彩光晕，浅景深，柔和散景，大师级摄影作品',
	'可爱的3D黏土质感小猫宇航员，漂浮在浩瀚太空中，周围环绕着彩色星球与星云，皮克斯动画风格，柔和影棚光，C4D渲染'
];

function fillSamplePrompt() {
	const random = SAMPLE_PROMPTS[Math.floor(Math.random() * SAMPLE_PROMPTS.length)];
	props.form.prompt = random;
	ElMessage.success(t('已填入灵感提示词'));
}

function fillDefaultNegativePrompt() {
	props.form.negativePrompt = '低分辨率, 畸形肢体, 模糊, 水印, 粗糙噪点, 变形, 多余手指, 瑕疵面容';
	ElMessage.success(t('已填入常用负向过滤词'));
}

function formatOptionsJson() {
	try {
		const parsed = JSON.parse(props.form.optionsText || '{}');
		props.form.optionsText = JSON.stringify(parsed, null, 2);
		ElMessage.success(t('高级参数 JSON 格式化成功'));
	} catch (e) {
		ElMessage.warning(t('JSON 语法有误，无法格式化'));
	}
}
</script>

<style lang="scss" scoped>
.generator {
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
		padding: 12px 16px;
		background: var(--el-fill-color-blank);
		border-bottom: 1px solid var(--el-border-color-lighter);
		flex-shrink: 0;

		.head-info {
			display: flex;
			flex-direction: column;
			gap: 2px;
		}

		.head-title {
			display: flex;
			align-items: center;
			gap: 6px;

			.title-icon {
				font-size: 18px;
				color: var(--el-color-primary);
			}

			h2 {
				margin: 0;
				font-size: 16px;
				font-weight: 650;
				color: var(--el-text-color-primary);
			}
		}

		.head-summary {
			font-size: 11.5px;
			color: var(--el-text-color-secondary);
		}
	}

	&__body {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	&__footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 16px;
		background: var(--el-fill-color-blank);
		border-top: 1px solid var(--el-border-color-lighter);
		flex-shrink: 0;

		.footer-right {
			display: flex;
			align-items: center;
			gap: 10px;

			.generate-main-btn {
				font-weight: 600;
				padding: 8px 18px;
			}
		}
	}
}

.top-notice {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 8px 12px;
	background: var(--el-color-primary-light-9);
	border: 1px solid var(--el-color-primary-light-7);
	border-radius: 6px;
	font-size: 12px;
	color: var(--el-color-primary);

	&__body {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.close-icon {
		cursor: pointer;
		opacity: 0.7;
		&:hover {
			opacity: 1;
		}
	}
}

.config-card {
	background: var(--el-fill-color-blank);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	padding: 12px 14px;
	display: flex;
	flex-direction: column;
	gap: 10px;

	.card-header {
		display: flex;
		align-items: center;

		&.space-between {
			justify-content: space-between;
		}

		.card-title {
			font-size: 13.5px;
			font-weight: 600;
			color: var(--el-text-color-primary);
		}

		.title-with-tip {
			display: flex;
			align-items: center;
			gap: 6px;

			.title-tip-icon {
				color: var(--el-text-color-secondary);
				font-size: 14px;
				cursor: help;
			}
		}
	}

	.field-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 10px;

		&--compact {
			:deep(.el-form-item) {
				margin-bottom: 0;
				display: flex;
				flex-direction: column;
				align-items: flex-start;

				.el-form-item__label {
					font-size: 12px;
					height: 22px;
					line-height: 22px;
					padding-bottom: 2px;
					color: var(--el-text-color-regular);
				}
			}
		}
	}

	.profile-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-top: 2px;
	}
}

.prompt-box {
	position: relative;
	border: 1px solid var(--el-border-color);
	border-radius: 6px;
	overflow: hidden;

	.prompt-textarea {
		:deep(textarea) {
			border: none;
			box-shadow: none;
			padding: 8px 10px;
			font-size: 13px;
			line-height: 1.5;
		}
	}

	.prompt-footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 4px 10px 6px;
		background: var(--el-fill-color-extra-light);
		font-size: 11px;
		color: var(--el-text-color-secondary);

		.counter-tip.is-limit {
			color: var(--el-color-danger);
			font-weight: 600;
		}
	}
}

.field-tip.warning {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: 11.5px;
	color: var(--el-color-warning);
	background: var(--el-color-warning-light-9);
	padding: 6px 10px;
	border-radius: 4px;
}

.negative-prompt-box {
	margin-top: 4px;
	.sub-title {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-size: 12px;
		color: var(--el-text-color-regular);
		margin-bottom: 4px;
	}
}

.reference-input-area {
	.upload-wrapper {
		display: flex;
		flex-direction: column;
		gap: 4px;

		.upload-hint {
			font-size: 11.5px;
			color: var(--el-text-color-secondary);
		}
	}

	.url-input-wrapper {
		display: flex;
		flex-direction: column;
		gap: 8px;

		.url-image-preview {
			display: flex;
			align-items: center;
			gap: 10px;

			.preview-thumb {
				width: 48px;
				height: 48px;
				border-radius: 4px;
				border: 1px solid var(--el-border-color);
			}
		}
	}
}

.aspect-ratio-selector {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 12px;

	.ratio-label {
		color: var(--el-text-color-regular);
		flex-shrink: 0;
	}

	.ratio-chips {
		display: flex;
		gap: 6px;
		overflow-x: auto;

		.ratio-chip {
			display: inline-flex;
			align-items: center;
			gap: 4px;
			padding: 4px 8px;
			border: 1px solid var(--el-border-color-lighter);
			background: var(--el-fill-color-extra-light);
			border-radius: 4px;
			font-size: 11.5px;
			cursor: pointer;
			color: var(--el-text-color-regular);
			transition: all 0.15s;

			&:hover {
				border-color: var(--el-color-primary-light-5);
				color: var(--el-color-primary);
			}

			&.is-active {
				background: var(--el-color-primary-light-9);
				border-color: var(--el-color-primary);
				color: var(--el-color-primary);
				font-weight: 600;
			}
		}
	}
}

.config-card--collapse {
	:deep(.el-collapse) {
		border: none;
		.el-collapse-item__header {
			height: 32px;
			line-height: 32px;
			border: none;
			background: transparent;
			font-size: 12.5px;
		}
		.el-collapse-item__wrap {
			border: none;
			background: transparent;
		}
		.el-collapse-item__content {
			padding-bottom: 0;
		}
	}

	.collapse-title {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--el-text-color-regular);
		.collapse-sub {
			font-size: 11px;
			color: var(--el-text-color-secondary);
		}
	}

	.advanced-editor {
		display: flex;
		flex-direction: column;
		gap: 6px;

		.scenario-field {
			.field-label-row {
				display: flex;
				align-items: center;
				gap: 4px;
				font-size: 12px;
				color: var(--el-text-color-regular);
				margin-bottom: 4px;

				.title-tip-icon {
					cursor: help;
					font-size: 13px;
					color: var(--el-text-color-secondary);
				}
			}
		}

		.advanced-tools {
			display: flex;
			justify-content: space-between;
			align-items: center;
			font-size: 11px;
			color: var(--el-text-color-secondary);
		}
	}
}

.mb-10 {
	margin-bottom: 10px;
}
.mt-10 {
	margin-top: 10px;
}
.mr-2 {
	margin-right: 4px;
}
</style>
