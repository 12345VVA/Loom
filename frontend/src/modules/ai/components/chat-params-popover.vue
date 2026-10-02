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

import { Operation } from '@element-plus/icons-vue';
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
			font-size: 12px;
			color: var(--el-text-color-regular);
			margin-bottom: 4px;

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
