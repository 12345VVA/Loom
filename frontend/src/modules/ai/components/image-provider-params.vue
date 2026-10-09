<template>
	<div class="section">
		<div class="section__title">
			<span>{{ $t('厂商参数') }}</span>
			<el-tooltip :content="providerHint" placement="top" effect="dark">
				<el-icon class="title-tip-icon"><info-filled /></el-icon>
			</el-tooltip>
		</div>

		<div v-if="providerKind === 'bailian'" class="provider-panel">
			<el-checkbox v-model="form.promptExtend">{{
				$t('智能改写 prompt_extend')
			}}</el-checkbox>
			<el-checkbox v-model="form.forceAsync">{{ $t('强制异步') }}</el-checkbox>
		</div>

		<div v-else-if="providerKind === 'volcengine-ark'" class="provider-panel">
			<div class="field-grid field-grid--vertical">
				<el-form-item>
					<template #label>
						<span class="mr-4">guidance_scale</span>
						<el-tooltip
							:content="
								$t(
									'分类指导比例。值越大越贴近提示词，但过大可能导致画面发硬或色彩过饱和，推荐 5.0 - 10.0。'
								)
							"
							placement="top"
						>
							<el-icon class="label-tip-icon"><info-filled /></el-icon>
						</el-tooltip>
					</template>
					<el-input-number
						v-model="form.guidanceScale"
						:min="0"
						:max="20"
						:step="0.5"
						controls-position="right"
					/>
				</el-form-item>
				<el-form-item>
					<template #label>
						<span class="mr-4">sequential_image_generation</span>
						<el-tooltip
							:content="
								$t(
									'多图生成调度模式。disabled 表示并行生成；auto 表示自动调度，在生成大图或资源紧张时可提高成功率。'
								)
							"
							placement="top"
						>
							<el-icon class="label-tip-icon"><info-filled /></el-icon>
						</el-tooltip>
					</template>
					<cl-select
						v-model="form.sequentialImageGeneration"
						:options="SEQUENTIAL_OPTIONS"
						clearable
					/>
				</el-form-item>
			</div>
		</div>

		<div v-else-if="providerKind === 'openai'" class="provider-panel">
			<div class="field-grid">
				<el-form-item label="quality">
					<cl-select v-model="form.quality" :options="QUALITY_OPTIONS" clearable />
				</el-form-item>
				<el-form-item label="style">
					<cl-select v-model="form.style" :options="STYLE_OPTIONS" clearable />
				</el-form-item>
				<el-form-item :label="$t('思维思考')">
					<el-switch v-model="form.thinking" />
				</el-form-item>
			</div>
		</div>

		<div v-else-if="providerKind === 'poryf'" class="provider-panel">
			<div class="field-grid">
				<el-form-item label="quality">
					<cl-select v-model="form.quality" :options="PORYF_QUALITY_OPTIONS" clearable />
				</el-form-item>
				<el-form-item label="output_format">
					<cl-select v-model="form.outputFormat" :options="PORYF_OUTPUT_FORMAT_OPTIONS" clearable />
				</el-form-item>
			</div>
			<div class="field-tip warning">
				<el-icon><info-filled /></el-icon>
				<span>{{ $t('Poryf 参考图须 ≤1MB，超限会被本地直接拒绝；建议用 jpeg 小图降传输与计费。') }}</span>
			</div>
		</div>

		<div v-else-if="providerKind === 'qianfan'" class="provider-panel">
			<div class="field-tip">
				<el-icon><info-filled /></el-icon>
				<span>{{
					isErnieIrag
						? $t(
								'当前使用百度 ERNIE iRAG 检索增强模型。中文文本准确度高，支持参考图，Prompt 限制 220 字符；不支持负向提示词与随机种子。'
							)
						: $t(
								'当前使用百度千帆 V2 接口。支持负向提示词与随机种子（可在高级 JSON 设置）。'
							)
				}}</span>
			</div>
		</div>

		<div v-else-if="providerKind === 'gemini'" class="provider-panel">
			<div class="field-tip">
				<el-icon><info-filled /></el-icon>
				<span>{{
					$t(
						'当前使用谷歌 Gemini 原生生图，已平滑支持 gemini-2.5-flash-image 替代 Imagen。支持参考图，可结合 text/image 多模态调用。'
					)
				}}</span>
			</div>
		</div>

		<div v-else class="field-tip warning">
			<el-icon><info-filled /></el-icon>
			<span>{{ $t('该厂商暂未配置专属参数，可使用通用参数和高级 JSON。') }}</span>
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-image-provider-params'
});

import { InfoFilled } from '@element-plus/icons-vue';
import {
	QUALITY_OPTIONS,
	PORYF_OUTPUT_FORMAT_OPTIONS,
	PORYF_QUALITY_OPTIONS,
	SEQUENTIAL_OPTIONS,
	STYLE_OPTIONS,
	type ImageProviderKind
} from '../utils/image-providers';
import type { ImageWorkbenchForm } from '../composables/use-image-workbench';

// form 为父级 reactive 表单的引用，嵌套字段直接读写（eslint 已关闭 vue/no-mutating-props）
defineProps<{
	form: ImageWorkbenchForm;
	providerKind: ImageProviderKind;
	providerHint: string;
	isErnieIrag: boolean;
}>();
</script>

<style lang="scss" scoped>
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

	&--vertical {
		grid-template-columns: 1fr;
	}
}

.provider-panel {
	:deep(.el-checkbox) {
		margin-right: 16px;
	}

	.label-tip-icon {
		margin-left: 4px;
		font-size: 14px;
		color: var(--el-text-color-placeholder);
		cursor: pointer;
		vertical-align: middle;
		transition: color 0.3s;

		&:hover {
			color: var(--el-color-primary);
		}
	}
}

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
