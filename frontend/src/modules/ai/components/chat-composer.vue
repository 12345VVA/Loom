<template>
	<footer class="composer-container">
		<div class="composer-box">
			<!-- 待发送图片缩略图条 -->
			<div v-if="pendingImages.length" class="pending-images">
				<div v-for="(img, idx) in pendingImages" :key="idx" class="pending-image-item">
					<el-image :src="img" fit="cover" />
					<button
						type="button"
						class="pending-image-remove"
						:title="$t('移除图片')"
						@click="$emit('remove-image', idx)"
					>
						<el-icon><close /></el-icon>
					</button>
				</div>
			</div>

			<el-input
				ref="inputRef"
				v-model="text"
				type="textarea"
				:autosize="{ minRows: 2, maxRows: 6 }"
				resize="none"
				class="chat-input"
				:placeholder="$t('输入您的问题，按 Enter 发送，Shift + Enter 换行...')"
				@keydown="handleKeydown"
				@paste="handlePaste"
			/>

			<div class="composer-bar">
				<div class="bar-left">
					<!-- 附加图片（当前模型支持视觉时显示） -->
					<el-upload
						v-if="canAttachImages"
						:show-file-list="false"
						multiple
						accept="image/png,image/jpeg,image/webp,image/gif"
						:http-request="handleUpload"
					>
						<el-button link size="small" class="attach-btn">
							<el-icon class="mr-2"><paperclip /></el-icon>
							{{ $t('附加图片') }}
						</el-button>
					</el-upload>
					<el-tooltip v-else :content="$t('当前模型不支持视觉输入')" placement="top">
						<span class="attach-disabled-hint">
							<el-icon><picture /></el-icon>
						</span>
					</el-tooltip>

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
import { Close, Paperclip, Picture, Promotion, VideoPause } from '@element-plus/icons-vue';

const props = withDefaults(
	defineProps<{
		modelValue: string;
		pendingImages?: string[];
		canAttachImages?: boolean;
		isBusy?: boolean;
		loading: {
			chat: boolean;
			stream: boolean;
		};
	}>(),
	{
		pendingImages: () => [],
		canAttachImages: false,
		isBusy: false
	}
);

const emit = defineEmits<{
	(e: 'update:modelValue', val: string): void;
	(e: 'send-chat'): void;
	(e: 'send-stream'): void;
	(e: 'stop-stream'): void;
	(e: 'add-files', files: File[]): void;
	(e: 'remove-image', idx: number): void;
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

async function handleUpload(options: any) {
	emit('add-files', [options.file]);
}

function handlePaste(e: ClipboardEvent) {
	if (!props.canAttachImages || !e.clipboardData?.files?.length) return;
	const files = Array.from(e.clipboardData.files).filter(f => f.type.startsWith('image/'));
	if (!files.length) return;
	e.preventDefault();
	emit('add-files', files);
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

		.pending-images {
			display: flex;
			flex-wrap: wrap;
			gap: 8px;
			padding: 10px 14px 0;

			.pending-image-item {
				position: relative;
				width: 64px;
				height: 64px;
				border: 1px solid var(--el-border-color-lighter);
				border-radius: 6px;
				overflow: hidden;

				.el-image {
					width: 100%;
					height: 100%;
				}

				.pending-image-remove {
					position: absolute;
					top: 2px;
					right: 2px;
					display: grid;
					place-items: center;
					width: 18px;
					height: 18px;
					border: none;
					border-radius: 50%;
					background: rgba(0, 0, 0, 0.55);
					color: #fff;
					cursor: pointer;
					font-size: 11px;

					&:hover {
						background: rgba(0, 0, 0, 0.75);
					}
				}
			}
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

			.bar-left {
				display: flex;
				align-items: center;
				gap: 10px;
				min-width: 0;
			}

			.attach-btn {
				font-size: 12.5px;
			}

			.attach-disabled-hint {
				display: inline-grid;
				place-items: center;
				width: 24px;
				height: 24px;
				border-radius: 4px;
				color: var(--el-text-color-placeholder);
				cursor: not-allowed;
			}

			.key-hint {
				font-size: 11.5px;
				color: var(--el-text-color-secondary);
				white-space: nowrap;
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
