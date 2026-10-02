<template>
	<footer class="composer-container">
		<div class="composer-box">
			<el-input
				ref="inputRef"
				v-model="text"
				type="textarea"
				:autosize="{ minRows: 2, maxRows: 6 }"
				resize="none"
				class="chat-input"
				:placeholder="$t('输入您的问题，按 Enter 发送，Shift + Enter 换行...')"
				@keydown="handleKeydown"
			/>

			<div class="composer-bar">
				<div class="bar-left">
					<span class="key-hint">{{ $t('Enter 发送 / Shift + Enter 换行') }}</span>
				</div>

				<div class="bar-right">
					<el-button link size="small" @click="text = ''">
						{{ $t('清空输入') }}
					</el-button>

					<!-- 普通发送 -->
					<el-button
						v-if="!isBusy"
						size="default"
						plain
						:loading="loading.chat"
						@click="$emit('send-chat')"
					>
						{{ $t('普通发送') }}
					</el-button>

					<!-- 流式发送 / 停止生成 -->
					<el-button
						v-if="loading.stream"
						type="danger"
						size="default"
						class="action-main-btn"
						@click="$emit('stop-stream')"
					>
						<el-icon class="mr-2"><video-pause /></el-icon>
						{{ $t('停止输出') }}
					</el-button>
					<el-button
						v-else
						type="primary"
						size="default"
						class="action-main-btn stream-btn"
						:loading="loading.chat"
						@click="$emit('send-stream')"
					>
						<el-icon class="mr-2"><promotion /></el-icon>
						{{ $t('流式发送') }}
					</el-button>
				</div>
			</div>
		</div>
	</footer>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'chat-composer'
});

import { computed, ref } from 'vue';
import { Promotion, VideoPause } from '@element-plus/icons-vue';

const props = withDefaults(
	defineProps<{
		modelValue: string;
		isBusy?: boolean;
		loading: {
			chat: boolean;
			stream: boolean;
		};
	}>(),
	{
		isBusy: false
	}
);

const emit = defineEmits<{
	(e: 'update:modelValue', val: string): void;
	(e: 'send-chat'): void;
	(e: 'send-stream'): void;
	(e: 'stop-stream'): void;
}>();

const inputRef = ref();

const text = computed({
	get: () => props.modelValue,
	set: val => emit('update:modelValue', val)
});

function handleKeydown(e: Event | KeyboardEvent) {
	if (e instanceof KeyboardEvent && e.key === 'Enter' && !e.shiftKey) {
		e.preventDefault();
		if (!props.isBusy) {
			emit('send-stream');
		}
	}
}

defineExpose({
	focus: () => inputRef.value?.focus()
});
</script>

<style lang="scss" scoped>
.composer-container {
	padding: 12px 24px 16px;
	background: var(--el-fill-color-blank);
	border-top: 1px solid var(--el-border-color-lighter);
	flex-shrink: 0;

	.composer-box {
		max-width: 860px;
		margin: 0 auto;
		border: 1px solid var(--el-border-color);
		border-radius: 8px;
		background: var(--el-bg-color);
		box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
		transition: border-color 0.2s, box-shadow 0.2s;

		&:focus-within {
			border-color: var(--el-color-primary);
			box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
		}

		:deep(.el-textarea__inner) {
			border: none;
			box-shadow: none;
			padding: 10px 14px;
			background: transparent;
			font-size: 14px;
			line-height: 1.5;
		}

		.composer-bar {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 6px 12px;
			border-top: 1px dashed var(--el-border-color-extra-light);
			background: var(--el-fill-color-extra-light);
			border-bottom-left-radius: 7px;
			border-bottom-right-radius: 7px;

			.key-hint {
				font-size: 11.5px;
				color: var(--el-text-color-secondary);
			}

			.bar-right {
				display: flex;
				align-items: center;
				gap: 8px;
			}
		}
	}
}
</style>
