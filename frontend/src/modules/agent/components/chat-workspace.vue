<template>
	<div class="agent-workspace" :class="[`is-${mode}`, { 'sidebar-open': isSidebarOpen }]">
		<!-- 左侧会话栏（standalone 独占；widget/embedded 收进顶栏下拉选择） -->
		<aside v-if="mode === 'standalone'" class="ws-side" :class="{ collapsed: !isSidebarOpen }">
			<template v-if="isSidebarOpen">
				<div class="ws-side__section">
					<div class="ws-side__title">{{ t('agent.session.selectProfile') }}</div>
					<el-select
						:model-value="currentProfileId"
						:placeholder="t('agent.session.profilePlaceholder')"
						filterable
						class="ws-side__select"
						@update:model-value="onAgentChange"
					>
						<el-option
							v-for="item in publishedProfiles"
							:key="item.id"
							:label="item.name"
							:value="item.id"
						/>
					</el-select>
				</div>

				<div class="ws-side__section ws-side__sessions">
					<div class="ws-side__title">
						{{ t('agent.session.history') }}
						<el-button link type="primary" size="small" @click="newSession()">
							{{ t('agent.session.new') }}
						</el-button>
					</div>
					<div class="ws-side__list">
						<div
							v-for="row in sessions"
							:key="row.id"
							class="ws-session-item"
							:class="{ active: row.id === currentSessionId }"
							@click="openSession(row)"
						>
							<span class="ws-session-item__title">{{ row.title || row.sessionCode }}</span>
							<el-icon class="ws-session-item__del" @click.stop="onDeleteSession(row)">
								<delete />
							</el-icon>
						</div>
						<div v-if="!sessions.length" class="ws-side__empty">{{ t('agent.session.empty') }}</div>
					</div>
				</div>
			</template>
			<el-button
				class="ws-side__toggle"
				circle
				size="small"
				:icon="isSidebarOpen ? Fold : Expand"
				@click="isSidebarOpen = !isSidebarOpen"
			/>
		</aside>

		<!-- 右侧消息面板 -->
		<main class="ws-main">
			<div class="ws-topbar">
				<div class="ws-topbar__left">
					<el-icon class="ws-topbar__icon"><opportunity /></el-icon>
					<el-tooltip :content="agentName" placement="bottom" :show-after="400">
						<span class="ws-topbar__name">{{ agentName }}</span>
					</el-tooltip>
					<el-tag v-if="running" type="success" size="small">
						{{ t('agent.workspace.receiving') }}
					</el-tag>
				</div>
				<div class="ws-topbar__right">
					<template v-if="mode !== 'standalone'">
						<el-select
							:model-value="currentProfileId"
							:placeholder="t('agent.workspace.selectAgent')"
							filterable
							size="small"
							class="ws-topbar__select"
							@update:model-value="onAgentChange"
						>
							<el-option
								v-for="item in publishedProfiles"
								:key="item.id"
								:label="item.name"
								:value="item.id"
							/>
						</el-select>
						<el-button type="primary" size="small" :icon="Plus" @click="newSession()">
							{{ t('agent.session.new') }}
						</el-button>
					</template>
					<el-button
						size="small"
						plain
						:disabled="!currentSessionId"
						:icon="Download"
						@click="exportSession"
					>
						{{ t('agent.workspace.export') }}
					</el-button>
					<el-button v-if="closable" circle size="small" :icon="Close" @click="emit('close')" />
				</div>
			</div>

			<div ref="messageListRef" v-loading="loadingHistory" class="ws-messages">
				<template v-if="messages.length">
					<chat-message v-for="(m, i) in messages" :key="m.id || `m-${i}`" :message="m" />
				</template>
				<div v-else-if="!running" class="ws-messages__empty">{{ t('agent.session.placeholder') }}</div>

				<!-- 本轮 run 分析面板：工具步骤时间线 + 统计（有内容才出现） -->
				<div v-if="showAnalysis" class="ws-analysis">
					<div class="ws-analysis__header" @click="analysisOpen = !analysisOpen">
						<el-icon :class="{ 'is-open': analysisOpen }"><arrow-right /></el-icon>
						<span>{{ t('agent.workspace.analysis') }}</span>
						<el-tag size="small" type="info" effect="plain">
							{{ t('agent.workspace.stepCount', { n: toolSteps.length }) }}
						</el-tag>
					</div>
					<el-collapse-transition>
						<div v-show="analysisOpen" class="ws-analysis__body">
							<div class="ws-analysis__stats">
								<el-tag v-if="elapsedMs !== null" size="small" type="success" effect="plain">
									{{ t('agent.workspace.elapsed') }}: {{ formatDuration(elapsedMs) }}
								</el-tag>
								<el-tag size="small" effect="plain">
									{{ t('agent.trace.modelCalls') }}: {{ modelCallsCount }}
								</el-tag>
								<el-tag size="small" type="warning" effect="plain">
									{{ t('agent.trace.toolRounds') }}: {{ toolRounds }}
								</el-tag>
								<el-tag v-if="tokenStats.totalTokens" size="small" type="primary" effect="plain">
									Token: {{ tokenStats.totalTokens }}
									({{ tokenStats.promptTokens }} / {{ tokenStats.completionTokens }})
								</el-tag>
							</div>
							<div
								v-for="step in toolSteps"
								:key="step.toolCallId"
								class="ws-step"
								:class="[step.status]"
							>
								<el-icon v-if="step.status === 'running'" class="is-loading"><loading /></el-icon>
								<el-icon v-else-if="step.status === 'done'"><circle-check /></el-icon>
								<el-icon v-else><circle-close /></el-icon>
								<span class="ws-step__name">{{ step.toolName }}</span>
								<span v-if="step.endTs" class="ws-step__time">
									{{ formatDuration(step.endTs - step.startTs) }}
								</span>
							</div>
						</div>
					</el-collapse-transition>
				</div>

				<!-- 工具调用中提示 + 流式草稿区（answer_reset 后由草稿缓冲清空） -->
				<div v-if="runningTool" class="ws-live-tool">
					<el-icon class="is-loading"><loading /></el-icon>
					{{ t('agent.session.toolRunning') }}：{{ runningTool.toolName }}
				</div>
				<div v-if="running && streamingText" class="ws-streaming">
					<span class="ws-streaming__loading"><span></span><span></span><span></span></span>
					<div class="ws-streaming__text" v-html="streamingRendered"></div>
				</div>
				<el-alert v-if="stopHint" :title="stopHint" type="warning" :closable="false" class="ws-stop-hint" />
			</div>

			<div class="ws-input">
				<el-input
					v-model="input"
					type="textarea"
					:autosize="{ minRows: 1, maxRows: 6 }"
					:disabled="running || !currentProfileId"
					:placeholder="t('agent.session.inputPlaceholder')"
					@keydown.ctrl.enter="onSend"
					@keydown.meta.enter="onSend"
				/>
				<div class="ws-input__actions">
					<span class="ws-input__hint">{{ t('agent.session.sendHint') }}</span>
					<el-button v-if="running" type="danger" :icon="VideoPause" @click="stop()">
						{{ t('agent.session.stop') }}
					</el-button>
					<el-button
						v-else
						type="primary"
						:icon="VideoPlay"
						:disabled="!input.trim() || !currentProfileId"
						@click="onSend"
					>
						{{ t('agent.session.send') }}
					</el-button>
				</div>
			</div>
		</main>
	</div>
</template>

<script lang="ts" setup name="agent-workspace">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
	ArrowRight,
	CircleCheck,
	CircleClose,
	Close,
	Delete,
	Download,
	Expand,
	Fold,
	Loading,
	Opportunity,
	Plus,
	VideoPause,
	VideoPlay
} from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import ChatMessage from './chat-message.vue';
import { renderMarkdown } from '../utils/markdown';
import { useAgentSession, type AgentSessionRow } from '../composables/use-agent-session';

type WorkspaceMode = 'standalone' | 'embedded' | 'widget';

withDefaults(
	defineProps<{
		mode?: WorkspaceMode;
		/** 显示右上角关闭按钮（widget 悬浮球 / 嵌入容器时） */
		closable?: boolean;
	}>(),
	{ mode: 'standalone', closable: false }
);

const emit = defineEmits<{ (e: 'close'): void }>();

const { t } = useI18n();
const {
	publishedProfiles,
	sessions,
	currentSessionId,
	currentProfileId,
	messages,
	running,
	runningTool,
	toolSteps,
	tokenStats,
	elapsedMs,
	modelCallsCount,
	toolRoundsFinal,
	stopHint,
	streamingText,
	loadProfiles,
	loadSessions,
	openSession,
	newSession,
	removeSession,
	send,
	stop
} = useAgentSession({ mode: 'published' });

const isSidebarOpen = ref(true);
const analysisOpen = ref(true);
const input = ref('');
const messageListRef = ref<HTMLDivElement>();
const loadingHistory = ref(false);

const agentName = computed(
	() => publishedProfiles.value.find(p => p.id === currentProfileId.value)?.name || t('agent.workspace.title')
);
const streamingRendered = computed(() => renderMarkdown(streamingText.value));
const showAnalysis = computed(() => running || toolSteps.value.length > 0 || modelCallsCount.value > 0);
// 模型调用/工具轮次：流中用本地计数，final 后以服务端权威口径为准
const toolRounds = computed(() => toolRoundsFinal.value ?? toolSteps.value.length);

function onAgentChange(id: number) {
	currentProfileId.value = id;
	newSession();
}

async function refresh() {
	loadingHistory.value = true;
	try {
		await Promise.all([loadProfiles(), loadSessions()]);
	} finally {
		loadingHistory.value = false;
	}
}

async function onSend() {
	const question = input.value.trim();
	if (!question || running.value) return;
	input.value = '';
	analysisOpen.value = true;
	await send(question);
}

async function onDeleteSession(row: AgentSessionRow) {
	try {
		await ElMessageBox.confirm(t('agent.workspace.deleteSessionConfirm'), t('agent.workspace.title'), {
			type: 'warning'
		});
	} catch {
		return;
	}
	try {
		await removeSession(row);
	} catch (err) {
		ElMessage.error((err instanceof Error ? err.message : '') || t('agent.workspace.deleteFailed'));
	}
}

/** 导出当前会话为 Markdown（纯前端，无后端依赖） */
function exportSession() {
	if (!messages.value.length) return;
	const lines: string[] = [`# ${agentName.value}`, ''];
	for (const m of messages.value) {
		if (m.role === 'user') {
			lines.push(`## ${t('agent.workspace.roleUser')}`, '', m.content ?? '', '');
		} else if (m.role === 'assistant') {
			lines.push(`## ${t('agent.workspace.roleAssistant')}`, '', m.content ?? '', '');
		} else if (m.role === 'tool') {
			lines.push(`> ${t('agent.workspace.roleTool')}: ${m.name ?? ''}`, '', '```', m.content ?? '', '```', '');
		}
	}
	const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = `agent-session-${currentSessionId.value ?? 'draft'}.md`;
	a.click();
	URL.revokeObjectURL(url);
	ElMessage.success(t('agent.workspace.exported'));
}

function formatDuration(ms: number) {
	if (ms < 1000) return `${ms}ms`;
	return `${(ms / 1000).toFixed(1)}s`;
}

watch(
	() => messages.value.length + streamingText.value.length + toolSteps.value.length,
	() => {
		nextTick(() => {
			messageListRef.value?.scrollTo({ top: messageListRef.value.scrollHeight });
		});
	}
);

onMounted(refresh);
</script>

<style lang="scss" scoped>
.agent-workspace {
	display: flex;
	height: 100%;
	background-color: var(--el-bg-color);
	overflow: hidden;

	&.is-widget {
		background: transparent;
	}
}

.ws-side {
	width: 250px;
	border-right: 1px solid var(--el-border-color-lighter);
	display: flex;
	flex-direction: column;
	flex-shrink: 0;
	position: relative;
	transition: width 0.2s;

	&.collapsed {
		width: 44px;
	}

	&__toggle {
		position: absolute;
		right: -14px;
		top: 14px;
		z-index: 2;
	}

	&__section {
		padding: 14px 12px;
		border-bottom: 1px solid var(--el-border-color-lighter);
	}

	&__sessions {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		border-bottom: none;
	}

	&__title {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-size: 13px;
		color: var(--el-text-color-secondary);
		margin-bottom: 8px;
	}

	&__select {
		width: 100%;
	}

	&__list {
		flex: 1;
		overflow-y: auto;
	}

	&__empty {
		color: var(--el-text-color-secondary);
		font-size: 13px;
		text-align: center;
		padding: 16px 0;
	}
}

.ws-session-item {
	padding: 8px 10px;
	border-radius: 6px;
	cursor: pointer;
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 4px;

	&:hover {
		background-color: var(--el-fill-color-light);

		.ws-session-item__del {
			visibility: visible;
		}
	}

	&.active {
		background-color: var(--el-color-primary-light-9);

		.ws-session-item__title {
			color: var(--el-color-primary);
		}
	}

	&__title {
		font-size: 13px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	&__del {
		visibility: hidden;
		color: var(--el-text-color-secondary);
		flex-shrink: 0;

		&:hover {
			color: var(--el-color-danger);
		}
	}
}

.ws-main {
	flex: 1;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.ws-topbar {
	display: flex;
	justify-content: space-between;
	align-items: center;
	padding: 10px 14px;
	border-bottom: 1px solid var(--el-border-color-lighter);

	&__left {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	&__icon {
		color: var(--el-color-primary);
		flex-shrink: 0;
	}

	&__name {
		font-size: 14px;
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	&__right {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
	}

	&__select {
		width: 180px;
	}
}

.ws-messages {
	flex: 1;
	overflow-y: auto;
	padding: 16px;

	&__empty {
		color: var(--el-text-color-secondary);
		text-align: center;
		margin-top: 18%;
	}
}

.ws-analysis {
	margin: 8px 0 12px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	background-color: var(--el-fill-color-extra-light);

	&__header {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 12px;
		font-size: 13px;
		color: var(--el-text-color-secondary);
		cursor: pointer;
		user-select: none;

		.el-icon {
			transition: transform 0.2s;

			&.is-open {
				transform: rotate(90deg);
			}
		}
	}

	&__body {
		padding: 0 12px 10px;
	}

	&__stats {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-bottom: 8px;
	}
}

.ws-step {
	display: flex;
	align-items: center;
	gap: 6px;
	padding: 4px 0;
	font-size: 13px;

	&.running .el-icon {
		color: var(--el-color-primary);
	}

	&.done .el-icon {
		color: var(--el-color-success);
	}

	&.skipped .el-icon {
		color: var(--el-color-info);
	}

	&__name {
		color: var(--el-text-color-primary);
	}

	&__time {
		color: var(--el-text-color-secondary);
		font-size: 12px;
	}
}

.ws-live-tool {
	display: flex;
	align-items: center;
	gap: 6px;
	color: var(--el-color-primary);
	font-size: 13px;
	margin: 8px 0;
}

.ws-streaming {
	display: flex;
	gap: 8px;
	max-width: 86%;
	margin: 8px 0;
	padding: 8px 12px;
	border-radius: 8px;
	background-color: var(--el-fill-color-light);

	&__loading {
		display: inline-flex;
		gap: 3px;
		align-items: center;
		flex-shrink: 0;

		span {
			width: 5px;
			height: 5px;
			border-radius: 50%;
			background-color: var(--el-color-primary);
			animation: ws-blink 1.2s infinite both;

			&:nth-child(2) {
				animation-delay: 0.2s;
			}

			&:nth-child(3) {
				animation-delay: 0.4s;
			}
		}
	}

	&__text {
		line-height: 1.6;
		word-break: break-word;
		min-width: 0;

		:deep(p) {
			margin: 0 0 6px;

			&:last-child {
				margin-bottom: 0;
			}
		}

		:deep(pre) {
			margin: 6px 0;
			padding: 8px 10px;
			border-radius: 6px;
			background-color: var(--el-fill-color-darker);
			overflow: auto;
			font-size: 12px;
		}
	}
}

@keyframes ws-blink {
	0%,
	80%,
	100% {
		opacity: 0.25;
	}

	40% {
		opacity: 1;
	}
}

.ws-stop-hint {
	margin: 8px 0;
}

.ws-input {
	border-top: 1px solid var(--el-border-color-lighter);
	padding: 12px;
}

.ws-input__actions {
	display: flex;
	justify-content: flex-end;
	align-items: center;
	gap: 8px;
	margin-top: 8px;

	.ws-input__hint {
		color: var(--el-text-color-secondary);
		font-size: 12px;
		margin-right: auto;
	}
}
</style>
