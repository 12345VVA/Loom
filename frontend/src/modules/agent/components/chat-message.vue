<template>
	<div class="chat-message" :class="[`is-${message.role}`, { 'is-pending': pending }]">
		<!-- 用户头像（右侧）或 助手头像（左侧） -->
		<div v-if="message.role === 'assistant' || message.role === 'tool'" class="avatar assistant-avatar">
			<el-icon><opportunity /></el-icon>
		</div>

		<div class="message-container">
			<!-- 顶部 Meta 信息条（角色名 + 时间戳） -->
			<div class="bubble-meta">
				<span class="role-name">{{ roleDisplayName }}</span>
				<span v-if="timeDisplay" class="time">{{ timeDisplay }}</span>
				<el-tag v-if="pending" size="small" type="success" effect="plain" class="pending-tag">
					{{ t('agent.workspace.generating') }}
				</el-tag>
			</div>

			<!-- 用户气泡（附件条在上方：图片缩略图 / 文本文件 chip——走查反馈附件上传分析） -->
			<template v-if="message.role === 'user'">
				<div v-if="attachments.length" class="attachments">
					<template v-for="att in attachments" :key="att.id">
						<el-image
							v-if="att.mime?.startsWith('image/')"
							:src="assetUrl(att.url)"
							fit="cover"
							class="attachment-thumb"
							:preview-src-list="[assetUrl(att.url)]"
							preview-teleported
							hide-on-click-modal
						/>
						<a v-else class="attachment-file" :href="assetUrl(att.url)" target="_blank" rel="noopener">
							<el-icon><document /></el-icon>
							<span class="attachment-file__name">{{ att.name }}</span>
							<span class="attachment-file__size">{{ formatSize(att.size) }}</span>
						</a>
					</template>
				</div>
				<div v-if="message.content" class="bubble user-bubble">
					{{ message.content }}
				</div>
			</template>

			<!-- 助手回复区域 -->
			<template v-else-if="message.role === 'assistant'">
				<!-- 1. Agent 分析（若该消息带有思维链/工具步骤） -->
				<div v-if="hasThoughtSteps" class="thought-process">
					<div class="thought-header" @click="thoughtOpen = !thoughtOpen">
						<el-icon :class="{ 'is-rotated': thoughtOpen }"><arrow-right /></el-icon>
						<span>{{ t('agent.workspace.analysis') }}</span>
						<el-tag size="small" type="info" effect="plain">
							{{ t('agent.workspace.stepCount', { n: message.thoughtSteps?.length || 0 }) }}
						</el-tag>
					</div>
					<el-collapse-transition>
						<div v-show="thoughtOpen" class="thought-body">
							<div
								v-for="(step, sIdx) in message.thoughtSteps"
								:key="sIdx"
								class="thought-step"
							>
								<div class="step-icon">
									<el-icon><cpu /></el-icon>
								</div>
								<div class="step-main">
									<div class="step-title">{{ step.title || step.toolName }}</div>
									<pre v-if="step.content" class="step-content"><code>{{ step.content }}</code></pre>
								</div>
							</div>
						</div>
					</el-collapse-transition>
				</div>

				<!-- 2. 参考资料（若消息带有知识库溯源引用） -->
				<div v-if="hasReferences" class="references-section">
					<div class="references-header" @click="refsOpen = !refsOpen">
						<div class="references-header-left">
							<el-icon :class="{ 'is-rotated': refsOpen }"><arrow-right /></el-icon>
							<span>{{ t('agent.workspace.references') }}</span>
						</div>
						<el-tag size="small" type="info" effect="plain">
							{{ message.references?.length || 0 }} 条
						</el-tag>
					</div>
					<el-collapse-transition>
						<div v-show="refsOpen" class="references-list">
							<div
								v-for="(refItem, rIdx) in message.references"
								:key="rIdx"
								class="reference-item"
							>
								<span class="reference-index">{{ rIdx + 1 }}</span>
								<span class="reference-title">{{ refItem.title || refItem.name }}</span>
								<el-tag size="small" :type="refItem.refType === 'file' ? 'success' : 'warning'">
									{{ refItem.refType === 'file' ? '文件' : '问答' }}
								</el-tag>
							</div>
						</div>
					</el-collapse-transition>
				</div>

				<!-- 3. 正式文本回复气泡 / 生成中波浪态 -->
				<div class="bubble assistant-bubble">
					<!-- 模型输出按 markdown 渲染 -->
					<div v-if="message.content" class="bubble-markdown" v-html="rendered"></div>

					<!-- 生成中优雅动效：左侧文字 + 右侧错峰呼吸波浪三点 -->
					<div v-else-if="pending" class="loading-state">
						<span class="loading-state__text">{{ t('agent.workspace.generatingReply') }}</span>
						<span class="loading-state__dots" aria-hidden="true">
							<span></span>
							<span></span>
							<span></span>
						</span>
					</div>

					<span v-else class="empty-text">（无文本回复）</span>
				</div>
			</template>

			<!-- 工具调用结果：可折叠块 -->
			<el-collapse v-else-if="message.role === 'tool'" class="tool-collapse">
				<el-collapse-item :name="message.toolCallId || message.id">
					<template #title>
						<span class="tool-title">
							<el-icon><set-up /></el-icon>
							工具结果：{{ message.name || '未知工具' }}
						</span>
					</template>
					<pre class="tool-content">{{ formatContent(message.content) }}</pre>
				</el-collapse-item>
			</el-collapse>
		</div>

		<div v-if="message.role === 'user'" class="avatar user-avatar">
			<el-icon><user /></el-icon>
		</div>
	</div>
</template>

<script lang="ts" setup name="agent-chat-message">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ArrowRight, Cpu, Document, Opportunity, SetUp, User } from '@element-plus/icons-vue';
import { renderMarkdown } from '../utils/markdown';
import { useAssetUrl } from '/$/media/composables/use-asset-url';
import type { AttachmentRef } from '../composables/use-agent-session';

const props = defineProps<{
	message: {
		id?: number;
		role: string;
		content?: string;
		name?: string;
		toolCallId?: string;
		createTime?: string;
		meta?: string | null;
		attachments?: AttachmentRef[];
		thoughtSteps?: Array<{ title?: string; toolName?: string; content?: string }>;
		references?: Array<{ title?: string; name?: string; refType?: string }>;
	};
	pending?: boolean;
}>();

const { t } = useI18n();
const { assetUrl } = useAssetUrl();

const attachments = computed<AttachmentRef[]>(() => props.message.attachments || []);

function formatSize(bytes?: number) {
	if (!bytes) return '';
	if (bytes < 1024) return `${bytes}B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
	return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

const thoughtOpen = ref(false);
const refsOpen = ref(false);

const rendered = computed(() => renderMarkdown(props.message.content));

const hasThoughtSteps = computed(() => Boolean(props.message.thoughtSteps && props.message.thoughtSteps.length > 0));
const hasReferences = computed(() => Boolean(props.message.references && props.message.references.length > 0));

const roleDisplayName = computed(() => {
	if (props.message.role === 'user') return t('agent.workspace.roleUser');
	if (props.message.role === 'assistant') return t('agent.workspace.roleAssistant');
	if (props.message.role === 'tool') return t('agent.workspace.roleTool');
	return props.message.role;
});

const timeDisplay = computed(() => {
	if (!props.message.createTime) return '';
	const d = new Date(props.message.createTime);
	if (isNaN(d.getTime())) return '';
	const h = String(d.getHours()).padStart(2, '0');
	const m = String(d.getMinutes()).padStart(2, '0');
	const s = String(d.getSeconds()).padStart(2, '0');
	return `${h}:${m}:${s}`;
});

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
	gap: 12px;
	margin-bottom: 22px;
	animation: messageFadeIn 0.25s ease-out;

	&.is-user {
		justify-content: flex-end;

		.message-container {
			align-items: flex-end;
		}

		.bubble-meta {
			flex-direction: row-reverse;
		}
	}

	&.is-assistant,
	&.is-tool {
		justify-content: flex-start;

		.message-container {
			align-items: flex-start;
		}
	}
}

.avatar {
	width: 38px;
	height: 38px;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 18px;
	flex-shrink: 0;
	margin-top: 2px;

	&.user-avatar {
		background: linear-gradient(135deg, #3b82f6, #2563eb);
		color: #fff;
		box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
	}

	&.assistant-avatar {
		background: linear-gradient(135deg, #10b981, #059669);
		color: #fff;
		box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
	}
}

.message-container {
	display: flex;
	flex-direction: column;
	gap: 6px;
	max-width: 86%;
}

.bubble-meta {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 12px;
	padding: 0 4px;

	.role-name {
		font-weight: 600;
		color: var(--el-text-color-regular);
	}

	.time {
		color: var(--el-text-color-placeholder);
	}

	.pending-tag {
		height: 18px;
		padding: 0 6px;
		font-size: 11px;
	}
}

.thought-process {
	width: 100%;
	background: rgba(248, 250, 252, 0.85);
	border: 1px solid #e2e8f0;
	border-radius: 10px;
	overflow: hidden;
	margin-bottom: 2px;

	.thought-header {
		padding: 8px 12px;
		font-size: 13px;
		color: #64748b;
		display: flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
		user-select: none;
		transition: background 0.2s;

		&:hover {
			background: #f1f5f9;
		}

		.el-icon {
			transition: transform 0.25s;

			&.is-rotated {
				transform: rotate(90deg);
			}
		}
	}

	.thought-body {
		padding: 8px 12px 10px;
		border-top: 1px solid #e2e8f0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.thought-step {
		display: flex;
		gap: 8px;
		font-size: 13px;

		.step-icon {
			color: #3b82f6;
			font-size: 15px;
			margin-top: 1px;
		}

		.step-main {
			flex: 1;

			.step-title {
				font-weight: 500;
				color: #334155;
			}

			.step-content {
				margin: 4px 0 0;
				padding: 6px 8px;
				background: #f1f5f9;
				border-radius: 6px;
				font-size: 11px;
				white-space: pre-wrap;
				word-break: break-all;
			}
		}
	}
}

.references-section {
	width: 100%;
	background: #f8fafc;
	border: 1px solid #e2e8f0;
	border-radius: 10px;
	overflow: hidden;
	margin-bottom: 2px;

	.references-header {
		padding: 8px 12px;
		font-size: 13px;
		color: #64748b;
		display: flex;
		align-items: center;
		justify-content: space-between;
		cursor: pointer;
		user-select: none;

		&-left {
			display: flex;
			align-items: center;
			gap: 6px;

			.el-icon {
				transition: transform 0.25s;

				&.is-rotated {
					transform: rotate(90deg);
				}
			}
		}
	}

	.references-list {
		padding: 6px 10px 10px;
		border-top: 1px solid #e2e8f0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.reference-item {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px 8px;
		border-radius: 6px;
		border: 1px solid #e2e8f0;
		background: #fff;
		font-size: 12px;

		.reference-index {
			width: 18px;
			height: 18px;
			border-radius: 50%;
			background: #eff6ff;
			color: #2563eb;
			display: flex;
			align-items: center;
			justify-content: center;
			font-weight: 600;
			font-size: 11px;
			flex-shrink: 0;
		}

		.reference-title {
			flex: 1;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
			color: #1e293b;
		}
	}
}

.bubble {
	padding: 12px 18px;
	line-height: 1.65;
	word-break: break-word;
	font-size: 14px;
	box-shadow: 0 4px 18px rgba(0, 0, 0, 0.04);
}

.user-bubble {
	background: linear-gradient(135deg, #3b82f6, #2563eb);
	color: #fff;
	border-radius: 18px 6px 18px 18px;
	box-shadow: 0 6px 20px rgba(59, 130, 246, 0.24);
}

.attachments {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	justify-content: flex-end;

	.attachment-thumb {
		width: 76px;
		height: 76px;
		border-radius: 10px;
		border: 1px solid var(--el-border-color-lighter);
		cursor: zoom-in;
	}

	.attachment-file {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		max-width: 220px;
		padding: 8px 10px;
		border-radius: 10px;
		border: 1px solid var(--el-border-color-lighter);
		background: var(--el-fill-color-blank);
		font-size: 12px;
		text-decoration: none;
		color: var(--el-text-color-primary);

		.el-icon {
			color: var(--el-color-primary);
			flex-shrink: 0;
		}

		&__name {
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}

		&__size {
			color: var(--el-text-color-placeholder);
			flex-shrink: 0;
		}

		&:hover {
			border-color: var(--el-color-primary-light-5);
		}
	}
}

.assistant-bubble {
	background-color: var(--el-fill-color-blank);
	border: 1px solid var(--el-border-color-lighter);
	color: var(--el-text-color-primary);
	border-radius: 6px 18px 18px 18px;

	.bubble-markdown {
		white-space: normal;

		:deep(p) {
			margin: 0 0 8px;
			&:last-child {
				margin-bottom: 0;
			}
		}

		:deep(pre) {
			margin: 8px 0;
			padding: 10px 12px;
			border-radius: 8px;
			background-color: var(--el-fill-color-darker);
			overflow: auto;
			font-size: 13px;
		}

		:deep(code) {
			font-family: var(--el-font-family, monospace);
		}

		:deep(table) {
			border-collapse: collapse;
			margin: 8px 0;
			th,
			td {
				border: 1px solid var(--el-border-color-lighter);
				padding: 6px 12px;
				font-size: 13px;
			}
		}

		:deep(a) {
			color: var(--el-color-primary);
		}

		:deep(blockquote) {
			margin: 8px 0;
			padding: 4px 12px;
			border-left: 3px solid var(--el-border-color);
			color: var(--el-text-color-secondary);
		}

		:deep(img) {
			max-width: 100%;
			border-radius: 6px;
		}
	}
}

/* 正在生成回复状态（严格对齐参考图 1） */
.loading-state {
	display: inline-flex;
	align-items: center;
	gap: 10px;
	min-height: 28px;
	color: #64748b;

	&__text {
		font-size: 13px;
		font-weight: 500;
		color: #475569;
	}

	&__dots {
		display: inline-flex;
		align-items: center;
		gap: 6px;

		span {
			width: 6px;
			height: 6px;
			border-radius: 50%;
			background: linear-gradient(135deg, #94a3b8, #64748b);
			animation: loadingDots 1.2s infinite ease-in-out;
			box-shadow: 0 0 0 2px rgba(148, 163, 184, 0.15);

			&:nth-child(2) {
				animation-delay: 0.15s;
			}

			&:nth-child(3) {
				animation-delay: 0.3s;
			}
		}
	}
}

.empty-text {
	color: var(--el-text-color-secondary);
	font-size: 13px;
}

.tool-collapse {
	width: 100%;
	border-radius: 8px;
	overflow: hidden;
	border: 1px solid var(--el-border-color-lighter);

	:deep(.el-collapse-item__header) {
		height: 36px;
		padding: 0 12px;
		font-size: 13px;
		background-color: var(--el-fill-color-light);
	}

	.tool-title {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: var(--el-text-color-secondary);
		font-weight: 500;
	}

	.tool-content {
		margin: 0;
		padding: 10px 12px;
		max-height: 240px;
		overflow: auto;
		font-size: 12px;
		white-space: pre-wrap;
		word-break: break-all;
		background-color: var(--el-fill-color-blank);
	}
}

@keyframes loadingDots {
	0%, 80%, 100% {
		transform: scale(0.6);
		opacity: 0.35;
	}
	40% {
		transform: scale(1.15);
		opacity: 1;
	}
}

@keyframes messageFadeIn {
	from {
		opacity: 0;
		transform: translateY(8px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}
</style>
