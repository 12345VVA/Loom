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
					<span>{{ $t('引用角色') }}:</span>
					<el-button
						v-if="referencedCharacter?.refImageUrl"
						link
						size="small"
						type="primary"
						:disabled="!canAttachImages"
						@click="rearmAssetRefImages"
					>
						{{ $t('重新携带参考图') }}
					</el-button>
				</div>
				<el-select
					:model-value="assetCharacterId ?? undefined"
					clearable
					filterable
					:placeholder="$t('选择角色（人设注入 + 首轮参考图）')"
					@update:model-value="(v: unknown) => onAssetCharacterChange(typeof v === 'number' ? v : null)"
				>
					<el-option
						v-for="a in assetCharacterOptions"
						:key="a.id"
						:label="`${a.name} (${a.code})`"
						:value="a.id"
					/>
				</el-select>
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

// 角色引用相关状态由 chat.vue 从 useChatWorkbench 解构后透传
const props = defineProps<{
	form: ChatFormState;
	assetCharacterOptions: { id: number; code: string; name: string; status: string; createdBy?: number | null }[];
	assetCharacterId: number | null;
	referencedCharacter: { name: string; voicePrompt?: string | null; refImageUrl?: string | null } | null;
	onAssetCharacterChange: (id: number | null) => void | Promise<void>;
	rearmAssetRefImages: () => void;
	canAttachImages: boolean;
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
