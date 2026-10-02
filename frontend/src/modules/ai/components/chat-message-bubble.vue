<template>
	<div class="message-row" :class="message.role">
		<!-- 头像 -->
		<div class="message-avatar">
			<el-icon v-if="message.role === 'user'"><user /></el-icon>
			<el-icon v-else class="ai-avatar-icon"><magic-stick /></el-icon>
		</div>

		<!-- 气泡内容 -->
		<div class="message-bubble-wrapper">
			<div class="message-header-info">
				<span class="role-name">{{ message.role === 'user' ? $t('我') : $t('AI 助手') }}</span>
				<span v-if="message.time" class="time-label">{{ message.time }}</span>
			</div>

			<div class="message-bubble">
				<!-- 用户气泡：纯文本保留换行 -->
				<div v-if="message.role === 'user'" class="user-text">
					{{ message.content }}
				</div>

				<!-- AI 气泡：Markdown 渲染 -->
				<div v-else class="assistant-content">
					<div
						v-if="message.content"
						class="markdown-body"
						v-html="renderMarkdown(message.content)"
					></div>
					<div v-else-if="loading" class="typing-placeholder">
						<span class="typing-dot"></span>
						<span class="typing-dot"></span>
						<span class="typing-dot"></span>
					</div>
					<span v-if="isStreaming" class="typing-cursor"></span>
				</div>
			</div>

			<!-- 气泡悬浮操作工具条 -->
			<div class="message-actions">
				<button
					type="button"
					class="bubble-action-btn"
					:title="$t('复制内容')"
					@click="copyText(message.content)"
				>
					<el-icon><copy-document /></el-icon>
				</button>

				<button
					v-if="message.role === 'assistant' && !isStreaming"
					type="button"
					class="bubble-action-btn"
					:title="$t('重新生成')"
					@click="$emit('regenerate', message.id)"
				>
					<el-icon><refresh /></el-icon>
				</button>

				<button
					type="button"
					class="bubble-action-btn"
					:title="$t('删除此条')"
					@click="$emit('remove', message.id)"
				>
					<el-icon><delete /></el-icon>
				</button>
			</div>
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'chat-message-bubble'
});

import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { User, MagicStick, CopyDocument, Refresh, Delete } from '@element-plus/icons-vue';
import { renderMarkdown } from '../utils/markdown-renderer';
import type { ChatMessageItem } from '../composables/use-chat-workbench';

const { t } = useI18n();

const props = withDefaults(
	defineProps<{
		message: ChatMessageItem;
		isStreaming?: boolean;
		loading?: boolean;
	}>(),
	{
		isStreaming: false,
		loading: false
	}
);

defineEmits<{
	(e: 'regenerate', id: number): void;
	(e: 'remove', id: number): void;
}>();

async function copyText(text: string) {
	if (!text) return;
	try {
		await navigator.clipboard.writeText(text);
		ElMessage.success(t('已复制到剪贴板'));
	} catch {
		ElMessage.warning(t('复制失败'));
	}
}
</script>

<style lang="scss" scoped>
.message-row {
	display: flex;
	gap: 12px;
	max-width: 860px;
	width: 100%;
	margin: 0 auto;
	position: relative;
	transition: opacity 0.2s;

	&.user {
		flex-direction: row-reverse;

		.message-bubble-wrapper {
			align-items: flex-end;
		}

		.message-bubble {
			background: var(--el-color-primary);
			color: #ffffff;
			border-radius: 12px 2px 12px 12px;
			box-shadow: 0 2px 8px rgba(var(--el-color-primary-rgb), 0.25);
		}

		.message-avatar {
			background: var(--el-color-primary-light-8);
			color: var(--el-color-primary);
		}
	}

	&.assistant {
		flex-direction: row;

		.message-bubble-wrapper {
			align-items: flex-start;
		}

		.message-bubble {
			background: var(--el-bg-color);
			color: var(--el-text-color-primary);
			border: 1px solid var(--el-border-color-lighter);
			border-radius: 2px 12px 12px 12px;
			box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
		}

		.message-avatar {
			background: linear-gradient(135deg, #ec4899, #8b5cf6);
			color: #ffffff;
		}
	}

	.message-avatar {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 18px;
		flex-shrink: 0;
	}

	.message-bubble-wrapper {
		display: flex;
		flex-direction: column;
		max-width: 80%;
		position: relative;

		&:hover .message-actions {
			opacity: 1;
			visibility: visible;
		}
	}

	.message-header-info {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-bottom: 4px;
		font-size: 11px;
		color: var(--el-text-color-secondary);

		.role-name {
			font-weight: 500;
		}
		.time-label {
			opacity: 0.8;
		}
	}

	.message-bubble {
		padding: 10px 14px;
		font-size: 14px;
		line-height: 1.6;
		word-break: break-word;

		.user-text {
			white-space: pre-wrap;
		}

		.assistant-content {
			position: relative;
		}
	}

	.message-actions {
		display: flex;
		align-items: center;
		gap: 4px;
		margin-top: 4px;
		opacity: 0;
		visibility: hidden;
		transition: all 0.2s;

		.bubble-action-btn {
			border: none;
			background: var(--el-fill-color);
			color: var(--el-text-color-secondary);
			width: 24px;
			height: 24px;
			border-radius: 4px;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 12px;
			cursor: pointer;
			transition: all 0.15s;

			&:hover {
				background: var(--el-fill-color-dark);
				color: var(--el-color-primary);
			}
		}
	}
}

.typing-placeholder {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	padding: 4px 0;

	.typing-dot {
		width: 6px;
		height: 6px;
		background: var(--el-text-color-secondary);
		border-radius: 50%;
		animation: dotBlink 1.4s infinite both;

		&:nth-child(2) {
			animation-delay: 0.2s;
		}
		&:nth-child(3) {
			animation-delay: 0.4s;
		}
	}
}

.typing-cursor {
	display: inline-block;
	width: 2px;
	height: 14px;
	background: var(--el-color-primary);
	vertical-align: middle;
	margin-left: 2px;
	animation: cursorBlink 0.8s infinite;
}

@keyframes dotBlink {
	0%,
	80%,
	100% {
		opacity: 0.3;
		transform: scale(0.8);
	}
	40% {
		opacity: 1;
		transform: scale(1.1);
	}
}

@keyframes cursorBlink {
	0%,
	100% {
		opacity: 1;
	}
	50% {
		opacity: 0;
	}
}

:deep(.markdown-body) {
	p {
		margin: 0 0 8px 0;
		&:last-child {
			margin-bottom: 0;
		}
	}

	pre {
		background: var(--el-fill-color-darker);
		color: #e6edf3;
		padding: 10px 12px;
		border-radius: 6px;
		overflow-x: auto;
		font-family: monospace;
		font-size: 13px;
		margin: 8px 0;
	}

	code {
		font-family: monospace;
		background: var(--el-fill-color);
		padding: 2px 4px;
		border-radius: 4px;
		font-size: 12.5px;
	}

	pre code {
		background: transparent;
		padding: 0;
	}

	ul,
	ol {
		padding-left: 20px;
		margin: 4px 0 8px 0;
	}

	table {
		border-collapse: collapse;
		width: 100%;
		margin: 8px 0;

		th,
		td {
			border: 1px solid var(--el-border-color);
			padding: 6px 10px;
			font-size: 13px;
		}
		th {
			background: var(--el-fill-color-light);
		}
	}
}
</style>
