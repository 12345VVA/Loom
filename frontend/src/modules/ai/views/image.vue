<template>
	<div class="ai-image-workbench">
		<section class="generator">
			<header class="generator__head">
				<div>
					<h2>{{ $t('AI 生图') }}</h2>
					<span>{{ selectedProfileSummary }}</span>
				</div>
				<el-tag :type="providerKindTag.type" effect="plain">{{
					providerKindTag.label
				}}</el-tag>
			</header>

			<div v-if="showTopNotice" class="top-notice">
				<div class="top-notice__body">
					<el-icon class="notice-icon"><bell /></el-icon>
					<span class="notice-text">
						{{
							$t('提示：不同模型支持的图生图、尺寸规格和专属参数存在差异，可悬停标题旁的')
						}}
						<el-icon class="inline-info-icon"><info-filled /></el-icon>
						{{ $t('图标查看具体说明。') }}
					</span>
				</div>
				<el-icon class="close-icon" @click="closeTopNotice"><close /></el-icon>
			</div>

			<div class="section">
				<div class="section__title">{{ $t('调用配置') }}</div>
				<div class="field-grid">
					<cl-select
						v-model="form.profileCode"
						:options="profileOptions"
						:placeholder="$t('默认图片配置')"
						clearable
					/>
					<el-input v-model="form.scenario" :placeholder="$t('场景')" clearable />
				</div>

				<div v-if="selectedProfile" class="profile-meta">
					<el-tag size="small">{{ selectedProfile.providerName || '-' }}</el-tag>
					<el-tag size="small" type="success">{{
						selectedProfile.modelName || selectedProfile.modelId
					}}</el-tag>
					<el-tag size="small" type="info">{{
						selectedProfile.modelType || 'image'
					}}</el-tag>
					<el-tag
						v-for="item in capabilityTags"
						:key="item"
						size="small"
						effect="plain"
						>{{ item }}</el-tag
					>
				</div>
			</div>

			<div class="section">
				<div class="section__title">{{ $t('提示词') }}</div>
				<cl-editor-markdown v-model="form.prompt" :height="260" simple />
				<div v-if="isErnieIrag && form.prompt.length > 220" class="field-tip warning mt-10">
					<el-icon><info-filled /></el-icon>
					<span>{{
						$t(
							'提示：当前为 ERNIE iRAG 检索增强生图，Prompt 长度超过限额（最大 220 字符），后端将自动截断。'
						)
					}}</span>
				</div>
				<div
					v-if="
						!isErnieIrag &&
						activeLimits.max_prompt_length &&
						form.prompt.length > activeLimits.max_prompt_length
					"
					class="field-tip warning mt-10"
				>
					<el-icon><info-filled /></el-icon>
					<span
						>{{ $t('提示：当前 Prompt 长度已超过模型推荐限制（最大') }}
						{{ activeLimits.max_prompt_length }} {{ $t('字符）。') }}</span
					>
				</div>
				<el-input
					v-if="showBailianNegativePrompt"
					v-model="form.negativePrompt"
					class="mt-10"
					type="textarea"
					:rows="3"
					:placeholder="$t('负向提示词，例如：低清晰度、畸形、文字水印')"
				/>
			</div>

			<div class="section">
				<div class="section__title">
					<span>{{ $t('参考图片 (图生图)') }}</span>
					<el-tooltip
						:content="
							$t('仅在火山方舟、阿里百炼和 OpenAI 兼容渠道等支持图生图的模型下生效。')
						"
						placement="top"
						effect="dark"
					>
						<el-icon class="title-tip-icon"><info-filled /></el-icon>
					</el-tooltip>
				</div>
				<el-radio-group v-model="imageInputMode" size="small" class="mb-10">
					<el-radio-button value="upload">{{ $t('本地上传') }}</el-radio-button>
					<el-radio-button value="url">{{ $t('网络地址') }}</el-radio-button>
				</el-radio-group>

				<div v-if="imageInputMode === 'upload'" class="mt-10">
					<cl-upload v-model="form.image" :limit="1" />
				</div>
				<div v-else class="mt-10">
					<el-input
						v-model="form.image"
						:placeholder="$t('请输入参考图片 URL')"
						clearable
					/>
				</div>
			</div>

			<div class="section">
				<div class="section__title">
					<span>{{ $t('通用参数') }}</span>
					<el-tooltip v-if="sizeHint" :content="sizeHint" placement="top" effect="dark">
						<el-icon class="title-tip-icon"><info-filled /></el-icon>
					</el-tooltip>
				</div>
				<div class="field-grid field-grid--compact">
					<el-form-item :label="$t('尺寸')">
						<cl-select v-model="form.size" :options="availableSizeOptions" />
					</el-form-item>
					<el-form-item :label="$t('数量')">
						<el-input-number
							v-model="form.n"
							:min="1"
							:max="activeLimits.max_n || 8"
							controls-position="right"
						/>
					</el-form-item>
					<el-form-item :label="$t('返回')">
						<cl-select v-model="form.responseFormat" :options="RESPONSE_FORMAT_OPTIONS" />
					</el-form-item>
					<el-form-item v-if="showWatermarkOption" :label="$t('水印')">
						<el-switch v-model="form.watermark" />
					</el-form-item>
				</div>
			</div>

			<image-provider-params
				:form="form"
				:provider-kind="providerKind"
				:provider-hint="providerHint"
				:is-ernie-irag="isErnieIrag"
			/>

			<div class="section">
				<el-collapse>
					<el-collapse-item :title="$t('高级参数 JSON')" name="advanced">
						<div class="advanced__head">
							<span>{{ $t('高级参数会最后合并，可覆盖表单参数') }}</span>
							<el-button text type="primary" @click="resetOptions">{{
								$t('重置')
							}}</el-button>
						</div>
						<el-input v-model="form.optionsText" type="textarea" :rows="8" />
					</el-collapse-item>
				</el-collapse>
			</div>

			<footer class="actions">
				<el-button @click="clearResult">{{ $t('清空结果') }}</el-button>
				<el-button :loading="loading.submit" type="warning" @click="submitTask">{{
					$t('异步提交')
				}}</el-button>
				<el-button :loading="loading.generate" type="primary" @click="generate">{{
					$t('生成图片')
				}}</el-button>
			</footer>
		</section>

		<aside class="result">
			<header>
				<div>
					<strong>{{ $t('生成结果') }}</strong>
					<span v-if="resultMeta.length">{{ resultMeta.join(' / ') }}</span>
				</div>
				<el-tag v-if="imageItems.length" size="small" type="success">{{
					imageItems.length
				}}</el-tag>
			</header>

			<div v-if="taskSubmitted" class="task-result">
				<el-result
					icon="success"
					:title="$t('任务已提交')"
					:sub-title="`Task ID: ${taskSubmitted.taskId}`"
				>
					<template #extra>
						<el-button type="primary" @click="copyText(String(taskSubmitted.taskId))">{{
							$t('复制任务 ID')
						}}</el-button>
					</template>
				</el-result>
			</div>

			<div v-else class="preview-list">
				<div v-for="(item, index) in imageItems" :key="index" class="preview-item">
					<el-image
						class="preview-image"
						:src="item.src"
						fit="contain"
						:preview-src-list="previewUrls"
						:initial-index="index"
						preview-teleported
					/>
					<div class="preview-actions">
						<el-button text type="primary" @click="copyText(item.value)">{{
							$t('复制')
						}}</el-button>
						<el-button v-if="item.url" text type="primary" @click="openUrl(item.url)">{{
							$t('打开')
						}}</el-button>
					</div>
				</div>
				<el-empty v-if="!imageItems.length" :description="$t('暂无图片')" />
			</div>

			<el-descriptions v-if="result" class="result-meta" border :column="2">
				<el-descriptions-item label="Provider">{{
					result.provider || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="Model">{{ result.model || '-' }}</el-descriptions-item>
				<el-descriptions-item label="Profile">{{
					result.profile || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="Request ID">{{
					result.requestId || result.taskId || '-'
				}}</el-descriptions-item>
			</el-descriptions>

			<el-tabs class="raw-tabs">
				<el-tab-pane :label="$t('请求')">
					<pre>{{ formatJson(lastPayload) }}</pre>
				</el-tab-pane>
				<el-tab-pane :label="$t('响应')">
					<pre>{{ formatJson(result) }}</pre>
				</el-tab-pane>
			</el-tabs>
		</aside>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-image'
});

import { ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { Bell, Close, InfoFilled } from '@element-plus/icons-vue';
import { RESPONSE_FORMAT_OPTIONS } from '../utils/image-providers';
import { useImageWorkbench } from '../composables/use-image-workbench';
import ImageProviderParams from '../components/image-provider-params.vue';

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
	clearResult
} = useImageWorkbench();

const showTopNotice = ref(localStorage.getItem('loom_ai_image_notice_closed') !== 'true');

function closeTopNotice() {
	showTopNotice.value = false;
	localStorage.setItem('loom_ai_image_notice_closed', 'true');
}

const imageInputMode = ref('upload');

watch(imageInputMode, () => {
	if (typeof form.image !== 'string') {
		form.image = '';
	}
});

async function copyText(value: string) {
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制'));
}

function openUrl(url: string) {
	window.open(url, '_blank');
}

function formatJson(value: any) {
	if (!value) {
		return '-';
	}
	return JSON.stringify(value, null, 2);
}
</script>

<style lang="scss" scoped>
.ai-image-workbench {
	display: grid;
	grid-template-columns: minmax(360px, 460px) minmax(0, 1fr);
	gap: 12px;
	height: 100%;
	min-height: 720px;
}

.generator,
.result {
	display: flex;
	min-height: 0;
	border: 1px solid var(--el-border-color-light);
	background: var(--el-bg-color);
}

.generator {
	flex-direction: column;
	overflow: auto;

	&__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 14px;
		border-bottom: 1px solid var(--el-border-color-light);

		h2 {
			margin: 0 0 4px;
			font-size: 18px;
			font-weight: 650;
		}

		span {
			color: var(--el-text-color-secondary);
			font-size: 13px;
		}
	}
}

.section {
	padding: 12px 14px;
	border-bottom: 1px solid var(--el-border-color-lighter);

	&__title {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-bottom: 10px;
		font-weight: 650;

		.title-tip-icon {
			font-size: 14px;
			color: var(--el-text-color-placeholder);
			cursor: pointer;
			transition: color 0.3s;

			&:hover {
				color: var(--el-color-primary);
			}
		}
	}
}

.field-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 10px;

	:deep(.el-form-item) {
		margin-bottom: 0;
	}

	&--compact {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}

.profile-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-top: 10px;
}

.advanced__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 8px;
	color: var(--el-text-color-secondary);
	font-size: 13px;
}

.mt-10 {
	margin-top: 10px;
}

.mb-10 {
	margin-bottom: 10px;
}

.actions {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
	padding: 12px 14px;
	margin-top: auto;
	border-top: 1px solid var(--el-border-color-light);
}

.result {
	flex-direction: column;

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 12px;
		border-bottom: 1px solid var(--el-border-color-light);

		div {
			display: grid;
			gap: 4px;
		}

		span {
			color: var(--el-text-color-secondary);
			font-size: 13px;
		}
	}
}

.task-result {
	padding: 18px;
}

.preview-list {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 12px;
	min-height: 280px;
	max-height: 48vh;
	overflow: auto;
	padding: 12px;
}

.preview-item {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-blank);
}

.preview-image {
	display: block;
	width: 100%;
	height: 220px;
	background: var(--el-fill-color-lighter);
}

.preview-actions {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
	padding: 8px;
}

.result-meta {
	margin: 0 12px 12px;
}

.raw-tabs {
	min-height: 0;
	padding: 0 12px 12px;

	pre {
		max-height: 260px;
		margin: 0;
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 12px;
	}
}

@media (max-width: 960px) {
	.ai-image-workbench {
		grid-template-columns: 1fr;
		height: auto;
	}
}

/* 顶部统一提示栏样式 */
.top-notice {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 12px;
	margin: 10px 14px 2px;
	padding: 10px 12px;
	background: var(--el-color-primary-light-9);
	border: 1px solid var(--el-color-primary-light-8);
	border-radius: 6px;
	transition: all 0.3s ease;

	&__body {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		color: var(--el-color-primary);
		font-size: 12px;
		line-height: 1.5;

		.notice-icon {
			font-size: 16px;
			margin-top: 1px;
			flex-shrink: 0;
		}

		.inline-info-icon {
			font-size: 13px;
			vertical-align: middle;
			margin: 0 2px;
			color: var(--el-color-primary);
		}
	}

	.close-icon {
		font-size: 14px;
		color: var(--el-color-primary-light-3);
		cursor: pointer;
		margin-top: 2px;
		transition: color 0.2s;

		&:hover {
			color: var(--el-color-primary);
		}
	}
}

/* 局部内联精致提示 */
.field-tip {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	margin-top: 10px;
	padding: 8px 10px;
	background: var(--el-fill-color-lighter);
	border-left: 3px solid var(--el-color-info);
	border-radius: 4px;
	color: var(--el-text-color-secondary);
	font-size: 12px;
	line-height: 1.4;

	.el-icon {
		color: var(--el-text-color-placeholder);
		font-size: 14px;
		margin-top: 1px;
		flex-shrink: 0;
	}

	&.warning {
		background: var(--el-color-warning-light-9);
		border-left-color: var(--el-color-warning);
		color: var(--el-color-warning-active);

		.el-icon {
			color: var(--el-color-warning);
		}
	}
}
</style>
