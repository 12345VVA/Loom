<template>
	<el-popover placement="bottom-end" :width="320" trigger="click">
		<template #reference>
			<el-button plain size="small">
				<el-icon class="mr-2"><operation /></el-icon>
				{{ $t('推理参数') }}
			</el-button>
		</template>
		<div class="params-popover">
			<div class="popover-title">{{ $t('模型推理参数调节') }}</div>

			<div class="param-item">
				<div class="param-header">
					<span>Temperature ({{ $t('随机性/创造力') }}):</span>
					<span class="param-val">{{ form.temperature }}</span>
				</div>
				<el-slider
					v-model="form.temperature"
					:min="0"
					:max="2"
					:step="0.1"
					:show-tooltip="true"
				/>
			</div>

			<div class="param-item">
				<div class="param-header">
					<span>Max Tokens ({{ $t('最大输出') }}):</span>
				</div>
				<el-input-number
					v-model="form.maxTokens"
					:min="64"
					:max="8192"
					:step="128"
					controls-position="right"
					style="width: 100%"
				/>
			</div>

			<div class="param-item">
				<div class="param-header">
					<span>{{ $t('系统提示词 (System Prompt)') }}:</span>
				</div>
				<el-input
					v-model="form.systemPrompt"
					type="textarea"
					:rows="3"
					resize="none"
					:placeholder="$t('设定 AI 的角色或语气设定...')"
				/>
			</div>

			<div class="param-item">
				<div class="param-header">
					<div class="param-label-with-tip">
						<span>{{ $t('业务场景 (Scenario)') }}:</span>
						<el-tooltip :content="$t('未指定配置时按此场景路由默认模型，亦用于审计日志归类')" placement="top">
							<el-icon class="tip-icon"><question-filled /></el-icon>
						</el-tooltip>
					</div>
				</div>
				<el-input
					v-model="form.scenario"
					:placeholder="$t('默认为 default')"
					clearable
				/>
			</div>

			<div class="param-item switch-item">
				<span>{{ $t('携带上下文历史') }}</span>
				<el-switch v-model="form.carryContext" />
			</div>
		</div>
	</el-popover>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'chat-params-popover'
});

import { Operation, QuestionFilled } from '@element-plus/icons-vue';
import type { ChatFormState } from '../composables/use-chat-workbench';

defineProps<{
	form: ChatFormState;
}>();
</script>

<style lang="scss" scoped>
.params-popover {
	.popover-title {
		font-weight: 600;
		font-size: 13px;
		margin-bottom: 12px;
		padding-bottom: 6px;
		border-bottom: 1px solid var(--el-border-color-lighter);
		color: var(--el-text-color-primary);
	}

	.param-item {
		margin-bottom: 12px;

		.param-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			font-size: 12px;
			color: var(--el-text-color-regular);
			margin-bottom: 4px;

			.param-label-with-tip {
				display: flex;
				align-items: center;
				gap: 4px;

				.tip-icon {
					cursor: help;
					font-size: 13px;
					color: var(--el-text-color-secondary);
				}
			}

			.param-val {
				font-family: monospace;
				font-weight: 600;
				color: var(--el-color-primary);
			}
		}

		&.switch-item {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 0;
			font-size: 12.5px;
			color: var(--el-text-color-regular);
		}
	}
}
</style>
