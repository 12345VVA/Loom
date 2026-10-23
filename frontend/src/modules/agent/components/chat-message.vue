<template>
	<div class="chat-message" :class="`is-${message.role}`">
		<div v-if="message.role === 'user'" class="bubble user-bubble">{{ message.content }}</div>

		<template v-else-if="message.role === 'assistant'">
			<div class="bubble assistant-bubble">
				{{ message.content }}
				<span v-if="!message.content" class="empty-text">（无文本回复）</span>
			</div>
		</template>

		<!-- 工具调用结果：可折叠块（tool_name/参数摘要不回显——结果摘要即可读） -->
		<el-collapse v-else-if="message.role === 'tool'" class="tool-collapse">
			<el-collapse-item :name="message.toolCallId || message.id">
				<template #title>
					<span class="tool-title">
						<el-icon><SetUp /></el-icon>
						工具结果：{{ message.name || '未知工具' }}
					</span>
				</template>
				<pre class="tool-content">{{ formatContent(message.content) }}</pre>
			</el-collapse-item>
		</el-collapse>
	</div>
</template>

<script lang="ts" setup name="agent-chat-message">
import { SetUp } from '@element-plus/icons-vue';

defineProps<{
	message: {
		id?: number;
		role: string;
		content?: string;
		name?: string;
		toolCallId?: string;
	};
}>();

function formatContent(content?: string) {
	if (!content) return '';
	try {
		return JSON.stringify(JSON.parse(content), null, 2);
	} catch {
		return content;
	}
}
</script>

<style lang="scss" scoped>
.chat-message {
	display: flex;
	margin-bottom: 12px;

	&.is-user {
		justify-content: flex-end;
	}

	&.is-tool {
		justify-content: flex-start;
	}
}

.bubble {
	max-width: 76%;
	padding: 8px 12px;
	border-radius: 8px;
	line-height: 1.6;
	word-break: break-word;
	white-space: pre-wrap;
}

.user-bubble {
	background-color: var(--el-color-primary);
	color: #fff;
}

.assistant-bubble {
	background-color: var(--el-fill-color-light);
}

.empty-text {
	color: var(--el-text-color-secondary);
	font-size: 12px;
}

.tool-collapse {
	width: 100%;

	:deep(.el-collapse-item__header) {
		height: 32px;
		font-size: 13px;
	}

	.tool-title {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: var(--el-text-color-secondary);
	}

	.tool-content {
		margin: 0;
		max-height: 240px;
		overflow: auto;
		font-size: 12px;
		white-space: pre-wrap;
		word-break: break-all;
	}
}
</style>
