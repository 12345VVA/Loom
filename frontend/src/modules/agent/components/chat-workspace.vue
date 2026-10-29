<template>
	<div class="agent-workspace" :class="[`is-${effectiveMode}`, { 'sidebar-open': isSidebarOpen }]">
		<!-- 左侧会话栏（standalone 独占；widget/embedded 收进顶栏下拉选择；draft 调试无会话语义） -->
		<aside v-if="effectiveMode === 'standalone'" class="ws-side" :class="{ collapsed: !isSidebarOpen }">
			<div class="ws-side__header" :class="{ 'is-collapsed': !isSidebarOpen }">
				<template v-if="isSidebarOpen">
					<div class="ws-side__agent-row">
						<el-select
							:model-value="currentProfileId"
							:placeholder="t('agent.session.profilePlaceholder')"
							filterable
							size="small"
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
						<el-tag v-if="currentSessionId" size="small" type="success" effect="plain" class="ws-side__in-session-tag">
							{{ t('agent.workspace.inSession') }}
						</el-tag>
					</div>

					<div class="ws-side__toolbar">
						<el-tooltip :content="t('agent.workspace.newSessionTooltip')" placement="top">
							<el-button
								circle
								type="primary"
								size="small"
								:icon="Plus"
								class="ws-side__tool-btn"
								@click="newSession()"
							/>
						</el-tooltip>
						<el-tooltip :content="t('agent.workspace.refresh')" placement="top">
							<el-button
								circle
								size="small"
								:icon="Refresh"
								class="ws-side__tool-btn"
								@click="refresh"
							/>
						</el-tooltip>
						<el-tooltip :content="t('agent.workspace.collapseSidebar')" placement="top">
							<el-button
								circle
								size="small"
								:icon="Fold"
								class="ws-side__tool-btn"
								@click="isSidebarOpen = false"
							/>
						</el-tooltip>
					</div>
				</template>
				<template v-else>
					<el-tooltip :content="t('agent.workspace.expandSidebar')" placement="right">
						<el-button
							circle
							size="small"
							:icon="Expand"
							class="ws-side__collapsed-toggle"
							@click="isSidebarOpen = true"
						/>
					</el-tooltip>
				</template>
			</div>

			<div v-if="isSidebarOpen" class="ws-side__sessions">
				<div class="ws-side__title">
					<span>{{ t('agent.session.history') }}</span>
				</div>
				<div class="ws-side__list">
					<div
						v-for="row in sessions"
						:key="row.id"
						class="ws-session-item"
						:class="{ active: row.id === currentSessionId }"
						:title="row.title || row.sessionCode"
						@click="openSession(row)"
					>
						<div class="ws-session-item__main">
							<div class="ws-session-item__title">{{ row.title || row.sessionCode }}</div>
							<div class="ws-session-item__time">{{ formatSessionTime(row.lastMessageAt || row.createTime) }}</div>
						</div>
						<div class="ws-session-item__actions" @click.stop>
							<el-dropdown trigger="click" @command="(fmt: 'markdown'|'json'|'text') => exportSessionFormat(fmt, row)">
								<el-button type="success" plain size="small" circle :icon="Download" class="action-btn" />
								<template #dropdown>
									<el-dropdown-menu>
										<el-dropdown-item command="markdown">{{ t('agent.workspace.exportMd') }}</el-dropdown-item>
										<el-dropdown-item command="json">{{ t('agent.workspace.exportJson') }}</el-dropdown-item>
										<el-dropdown-item command="text">{{ t('agent.workspace.exportTxt') }}</el-dropdown-item>
									</el-dropdown-menu>
								</template>
							</el-dropdown>
							<el-button
								type="danger"
								plain
								size="small"
								circle
								:icon="Delete"
								class="action-btn"
								@click="onDeleteSession(row)"
							/>
						</div>
					</div>
					<div v-if="!sessions.length" class="ws-side__empty">{{ t('agent.session.empty') }}</div>
				</div>
			</div>

			<div v-else class="ws-side__collapsed-body">
				<div
					v-for="row in sessions.slice(0, 10)"
					:key="row.id"
					class="collapsed-session-dot"
					:class="{ active: row.id === currentSessionId }"
					:title="row.title || row.sessionCode"
					@click="openSession(row)"
				>
					{{ (row.title || row.sessionCode || 'S').slice(0, 1) }}
				</div>
			</div>
		</aside>

		<!-- 右侧消息面板 -->
		<main class="ws-main">
			<div class="ws-topbar">
				<div class="ws-topbar__left">

					<el-icon class="ws-topbar__icon"><opportunity /></el-icon>
					<el-tooltip :content="agentName" placement="bottom" :show-after="400">
						<span class="ws-topbar__name">{{ agentName }}</span>
					</el-tooltip>
					<el-tag v-if="running" type="success" size="small" class="ws-topbar__status-tag">
						{{ t('agent.workspace.receiving') }}
					</el-tag>
					<el-tooltip
						v-if="currentSessionTitle"
						:content="currentSessionTitle"
						placement="bottom"
						:show-after="400"
					>
						<el-tag type="info" size="small" effect="plain" class="ws-topbar__session-tag">
							{{ currentSessionTitle }}
						</el-tag>
					</el-tooltip>
				</div>
				<div class="ws-topbar__right">
					<template v-if="effectiveMode !== 'standalone' && !isDraft">
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

					<el-dropdown
						v-if="currentSessionId"
						trigger="click"
						@command="(fmt: 'markdown'|'json'|'text') => exportSessionFormat(fmt)"
					>
						<el-button size="small" plain :icon="Download">
							{{ t('agent.workspace.export') }}
						</el-button>
						<template #dropdown>
							<el-dropdown-menu>
								<el-dropdown-item command="markdown">{{ t('agent.workspace.exportMd') }}</el-dropdown-item>
								<el-dropdown-item command="json">{{ t('agent.workspace.exportJson') }}</el-dropdown-item>
								<el-dropdown-item command="text">{{ t('agent.workspace.exportTxt') }}</el-dropdown-item>
							</el-dropdown-menu>
						</template>
					</el-dropdown>

					<el-button
						v-if="currentSessionId && messages.length"
						type="info"
						size="small"
						plain
						:icon="Delete"
						@click="clearCurrentSessionMessages"
					>
						{{ t('agent.workspace.clearHistory') }}
					</el-button>

					<el-button v-if="closable" circle size="small" :icon="Close" @click="emit('close')" />
				</div>
			</div>

			<div ref="messageListRef" v-loading="loadingHistory" class="ws-messages">
				<div class="ws-content-container">
					<template v-if="messages.length">
						<chat-message v-for="(m, i) in messages" :key="m.id || `m-${i}`" :message="m" />
					</template>
					<template v-else-if="!running">
						<agent-welcome
							v-if="currentProfileId"
							:profile="currentProfile"
							@select-starter="onSelectStarter"
						/>
						<div v-else class="ws-messages__empty">
							{{ emptyText }}
						</div>
					</template>

					<!-- 流式中的 assistant 回复以同构气泡渲染（final 重拉后无视觉跳变） -->
					<chat-message
						v-if="running"
						:message="{ role: 'assistant', content: streamingText }"
						:pending="true"
					/>

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

					<!-- 工具调用中提示 + 流式草稿区 -->
					<div v-if="runningTool" class="ws-live-tool">
						<el-icon class="is-loading"><loading /></el-icon>
						{{ t('agent.session.toolRunning') }}：{{ runningTool.toolName }}
					</div>
						<el-alert v-if="stopHint" :title="stopHint" type="warning" :closable="false" class="ws-stop-hint" />
					<!-- E4 审批挂起等待态（恢复轮询驱动终局刷新；停止按钮对挂起 run 仍有效） -->
					<el-alert
						v-if="awaitingApproval"
						:title="awaitingApproval.message"
						type="info"
						:closable="false"
						class="ws-stop-hint"
					/>
				</div>
			</div>

			<!-- 内嵌式轻快复合输入框 -->
			<div class="ws-input-wrapper">
				<div class="ws-content-container">
					<div class="chat-input-card">
						<!-- 待发送附件条（已上传 media 引用；走查反馈：图片视觉 + 文本注入） -->
						<div v-if="pendingAttachments.length" class="pending-attachments">
							<div v-for="(att, i) in pendingAttachments" :key="att.id" class="pending-attachment">
								<el-image
									v-if="att.mime.startsWith('image/')"
									:src="assetUrl(att.url)"
									fit="cover"
									class="pending-attachment__thumb"
									:preview-src-list="[assetUrl(att.url)]"
									preview-teleported
								/>
								<div v-else class="pending-attachment__file">
									<el-icon><document /></el-icon>
									<span class="pending-attachment__name">{{ att.name }}</span>
								</div>
								<el-icon class="pending-attachment__remove" @click="removeAttachment(i)">
									<circle-close-filled />
								</el-icon>
							</div>
						</div>
						<el-input
							v-model="input"
							type="textarea"
							:autosize="{ minRows: 1, maxRows: 6 }"
							:disabled="running || !currentProfileId"
							:placeholder="isDraft ? t('agent.debug.inputPlaceholder') : t('agent.session.inputPlaceholder')"
							class="chat-input-textarea"
							@keydown="handleKeydown"
							@paste="onInputPaste"
						/>
						<el-button
							v-if="running"
							type="danger"
							size="small"
							:icon="VideoPause"
							class="inner-send-btn"
							@click="stop()"
						>
							{{ t('agent.session.stop') }}
						</el-button>
						<template v-else>
							<el-tooltip :content="t('agent.workspace.attach')" placement="top" :show-after="300">
								<el-button
									size="small"
									:icon="Paperclip"
									class="inner-attach-btn"
									:disabled="running || !currentProfileId"
									@click="triggerAttach"
								/>
							</el-tooltip>
							<el-button
								type="primary"
								size="small"
								:icon="VideoPlay"
								:disabled="(!input.trim() && !pendingAttachments.length) || !currentProfileId"
								class="inner-send-btn"
								@click="onSend"
							>
								{{ t('agent.session.send') }}
							</el-button>
						</template>
						<input
							ref="fileInputRef"
							type="file"
							multiple
							:accept="ATTACH_ACCEPT"
							class="ws-attach-input"
							@change="onFileChosen"
						/>
					</div>
				</div>
			</div>
		</main>
	</div>
</template>

<script lang="ts" setup name="agent-workspace">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';
import {
	ArrowRight,
	CircleCheck,
	CircleClose,
	CircleCloseFilled,
	Close,
	Delete,
	Document,
	Download,
	Expand,
	Fold,
	Loading,
	Opportunity,
	Paperclip,
	Plus,
	Refresh,
	VideoPause,
	VideoPlay
} from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import ChatMessage from './chat-message.vue';
import AgentWelcome from './agent-welcome.vue';
import { useAgentSession, type AgentSessionRow, type AttachmentRef } from '../composables/use-agent-session';
import { useAssetUrl } from '/$/media/composables/use-asset-url';

type WorkspaceMode = 'standalone' | 'embedded' | 'widget';

const props = withDefaults(
	defineProps<{
		mode?: WorkspaceMode;
		/** 显示右上角关闭按钮（widget 悬浮球 / 嵌入容器时） */
		closable?: boolean;
		/** 草稿调试模式（draft 调试台）：外部指定 profileId，隐藏会话/智能体选择 */
		draftProfileId?: number | null;
	}>(),
	{ mode: 'standalone', closable: false, draftProfileId: null }
);

const emit = defineEmits<{ (e: 'close'): void }>();

const { service } = useCool();
const route = useRoute();

const { t } = useI18n();

// draft 调试台按组件实例静态确定（随 drawer v-if 重建），不随 props 动态切换
const isDraft = props.draftProfileId != null;
const effectiveMode = computed(() => (isDraft ? 'embedded' : props.mode));

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
	awaitingApproval,
	streamingText,
	loadProfiles,
	loadSessions,
	openSession,
	newSession,
	removeSession,
	send,
	stop
} = useAgentSession({ mode: isDraft ? 'draft' : 'published' });

// draft 模式：外部指定的 profileId 同步进会话状态（唯一 profileId 入口）
watch(
	() => props.draftProfileId,
	v => {
		if (v != null) currentProfileId.value = v;
	},
	{ immediate: true }
);

const isSidebarOpen = ref(true);
const analysisOpen = ref(true);
const input = ref('');
const messageListRef = ref<HTMLDivElement>();
const loadingHistory = ref(false);

// ---- 附件（走查反馈：图片走视觉、文本文件解码注入；限制对齐 ai 对话测试页口径）----
const { assetUrl } = useAssetUrl();
const pendingAttachments = ref<AttachmentRef[]>([]);
const fileInputRef = ref<HTMLInputElement>();
const ATTACH_ACCEPT =
	'image/png,image/jpeg,image/webp,image/gif,text/plain,text/markdown,text/csv,application/json,text/html,text/xml,' +
	'.txt,.md,.markdown,.csv,.json,.log,.py,.js,.ts,.sql,.yaml,.yml,.xml,.html';
const ATTACH_MIME_WHITELIST = [
	'image/png',
	'image/jpeg',
	'image/webp',
	'image/gif',
	'text/plain',
	'text/markdown',
	'text/csv',
	'application/json',
	'text/html',
	'text/xml'
];
const ATTACH_EXT_WHITELIST = [
	'.txt', '.md', '.markdown', '.csv', '.json', '.log', '.py',
	'.js', '.ts', '.sql', '.yaml', '.yml', '.xml', '.html',
	'.png', '.jpg', '.jpeg', '.webp', '.gif'
];
const ATTACH_MAX_COUNT = 4;
const ATTACH_MAX_SIZE_MB = 5;

function attachmentAllowed(file: File) {
	const mime = (file.type || '').split(';')[0].toLowerCase();
	if (ATTACH_MIME_WHITELIST.includes(mime)) return true;
	const name = file.name.toLowerCase();
	return ATTACH_EXT_WHITELIST.some(ext => name.endsWith(ext));
}

function triggerAttach() {
	fileInputRef.value?.click();
}

function onFileChosen(e: Event) {
	const inputEl = e.target as HTMLInputElement;
	const files = Array.from(inputEl.files || []);
	inputEl.value = ''; // 允许重复选择同一文件
	addAttachmentFiles(files);
}

function onInputPaste(e: ClipboardEvent | Event) {
	const files = (e as ClipboardEvent).clipboardData?.files;
	if (!files?.length) return;
	const images = Array.from(files).filter(f => f.type.startsWith('image/'));
	if (images.length) {
		e.preventDefault();
		addAttachmentFiles(images);
	}
}

async function addAttachmentFiles(files: File[]) {
	if (!files.length) return;
	const room = ATTACH_MAX_COUNT - pendingAttachments.value.length;
	if (room <= 0) {
		ElMessage.warning(t('agent.workspace.attachLimit', { n: ATTACH_MAX_COUNT }));
		return;
	}
	const accepted = files.filter(f => {
		if (!attachmentAllowed(f)) {
			ElMessage.warning(t('agent.workspace.attachTypeUnsupported', { name: f.name }));
			return false;
		}
		if (f.size > ATTACH_MAX_SIZE_MB * 1024 * 1024) {
			ElMessage.warning(t('agent.workspace.attachTooLarge', { name: f.name }));
			return false;
		}
		return true;
	});
	for (const file of accepted.slice(0, room)) {
		try {
			const form = new FormData();
			form.append('file', file);
			// URL 介质原则：先上传 media 拿引用再发送（use-test-form uploadImage 同款）
			const res = await service.media.asset.request({ url: '/upload', method: 'POST', data: form });
			pendingAttachments.value.push({
				id: res.id,
				name: file.name,
				mime: file.type || 'application/octet-stream',
				size: file.size,
				url: res.url
			});
		} catch (err) {
			ElMessage.error((err instanceof Error ? err.message : '') || t('agent.workspace.attachUploadFail'));
		}
	}
}

function removeAttachment(index: number) {
	pendingAttachments.value.splice(index, 1);
}

watch(currentSessionId, () => {
	// 会话切换（含新会话/run 回填 id）清空待发送附件——附件只随一次发送消费
	pendingAttachments.value = [];
});

const currentProfile = computed(() =>
	publishedProfiles.value.find(p => p.id === currentProfileId.value) || null
);

const agentName = computed(
	() =>
		(isDraft && t('agent.debug.title')) ||
		publishedProfiles.value.find(p => p.id === currentProfileId.value)?.name ||
		t('agent.workspace.title')
);

const currentSessionTitle = computed(() => {
	if (!currentSessionId.value) return '';
	const current = sessions.value.find(s => s.id === currentSessionId.value);
	return current?.title || current?.sessionCode || '';
});

const emptyText = computed(() => {
	if (isDraft) return t('agent.debug.empty');
	if (!currentProfileId.value) return t('agent.session.placeholder');
	return t('agent.session.newChatHint');
});

const showAnalysis = computed(() => running.value || toolSteps.value.length > 0 || modelCallsCount.value > 0);
const toolRounds = computed(() => toolRoundsFinal.value ?? toolSteps.value.length);

async function onAgentChange(id: number) {
	if (currentSessionId.value != null) {
		try {
			await ElMessageBox.confirm(
				t('agent.workspace.switchAgentConfirm'),
				t('agent.workspace.title'),
				{ type: 'warning' }
			);
		} catch {
			return;
		}
	}
	currentProfileId.value = id;
	newSession();
}

async function refresh() {
	if (isDraft) return;
	loadingHistory.value = true;
	try {
		await loadProfiles();
		await loadSessions();
	} finally {
		loadingHistory.value = false;
	}
}

function onSelectStarter(prompt: string) {
	input.value = prompt;
	onSend();
}

function handleKeydown(e: Event | KeyboardEvent) {
	if (!('key' in e)) return;
	if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
		e.preventDefault();
		onSend();
	}
}

async function onSend() {
	const question = input.value.trim();
	if ((!question && !pendingAttachments.value.length) || running.value) return;
	input.value = '';
	analysisOpen.value = true;
	const attachments = [...pendingAttachments.value];
	pendingAttachments.value = [];
	await send(question, attachments);
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

async function clearCurrentSessionMessages() {
	if (!currentSessionId.value) return;
	try {
		await ElMessageBox.confirm(t('agent.workspace.clearConfirm'), t('agent.workspace.title'), {
			type: 'warning'
		});
	} catch {
		return;
	}
	messages.value = [];
	ElMessage.success(t('agent.workspace.clearHistory'));
}

function formatSessionTime(dateStr?: string) {
	if (!dateStr) return '';
	const d = new Date(dateStr);
	if (isNaN(d.getTime())) return '';
	const now = new Date();
	const diffMs = now.getTime() - d.getTime();
	const diffMin = Math.floor(diffMs / (1000 * 60));
	const diffHour = Math.floor(diffMs / (1000 * 60 * 60));
	const diffDay = Math.floor(diffMs / (1000 * 60 * 60 * 24));

	if (diffMin < 1) return '刚刚';
	if (diffMin < 60) return `${diffMin}分钟前`;
	if (diffHour < 24) return `${diffHour}小时前`;
	if (diffDay < 7) return `${diffDay}天前`;

	const m = String(d.getMonth() + 1).padStart(2, '0');
	const day = String(d.getDate()).padStart(2, '0');
	return `${m}-${day}`;
}

function exportSessionFormat(format: 'markdown' | 'json' | 'text', targetSession?: AgentSessionRow) {
	const sId = targetSession?.id || currentSessionId.value;
	const sTitle = targetSession?.title || currentSessionTitle.value || agentName.value;
	const exportMessages = messages.value;
	if (!exportMessages.length) return;

	let content = '';
	let mime = 'text/plain;charset=utf-8';
	let ext = 'txt';

	if (format === 'markdown') {
		const lines: string[] = [`# ${sTitle}`, ''];
		for (const m of exportMessages) {
			if (m.role === 'user') {
				lines.push(`## ${t('agent.workspace.roleUser')}`, '', m.content ?? '', '');
				for (const att of m.attachments || []) {
					lines.push(
						att.mime.startsWith('image/') ? `![${att.name}](${assetUrl(att.url)})` : `- ${att.name} (${att.mime})`
					);
				}
				if (m.attachments?.length) lines.push('');
			} else if (m.role === 'assistant') {
				lines.push(`## ${t('agent.workspace.roleAssistant')}`, '', m.content ?? '', '');
			} else if (m.role === 'tool') {
				lines.push(`> ${t('agent.workspace.roleTool')}: ${m.name ?? ''}`, '', '```', m.content ?? '', '```', '');
			}
		}
		content = lines.join('\n');
		mime = 'text/markdown;charset=utf-8';
		ext = 'md';
	} else if (format === 'json') {
		content = JSON.stringify(exportMessages, null, 2);
		mime = 'application/json;charset=utf-8';
		ext = 'json';
	} else {
		content = exportMessages.map(m => `[${m.role}]: ${m.content || ''}`).join('\n\n');
	}

	const blob = new Blob([content], { type: mime });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = `agent-session-${sId ?? 'draft'}.${ext}`;
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

onMounted(async () => {
	await refresh();
	await openFromQuery();
});

/** 深链定位（调用追踪「查看会话」跳转）：?sessionId= 直开对应会话；失败保持默认初始化 */
async function openFromQuery() {
	const sessionId = Number(route.query.sessionId);
	if (!sessionId || isDraft) return;
	try {
		const row = (await service.agent.session.info({ id: sessionId })) as AgentSessionRow;
		await openSession(row);
	} catch {
		// 会话不存在/无权限——静默落回默认会话
	}
}

defineExpose({ refresh });
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
	width: 284px;
	background-color: var(--el-fill-color-blank);
	border-right: 1px solid var(--el-border-color-lighter);
	display: flex;
	flex-direction: column;
	flex-shrink: 0;
	position: relative;
	transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);

	&.collapsed {
		width: 52px;
	}

	&__header {
		padding: 12px 14px;
		border-bottom: 1px solid var(--el-border-color-lighter);
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;

		&.is-collapsed {
			justify-content: center;
			padding: 12px 0;
		}
	}

	&__collapsed-toggle {
		width: 32px;
		height: 32px;
		padding: 0;
		border-radius: 8px;
		font-size: 14px;
	}

	&__agent-row {
		display: flex;
		align-items: center;
		gap: 8px;
		flex: 1;
		min-width: 0;
	}

	&__select {
		flex: 1;
		min-width: 0;
	}

	&__in-session-tag {
		flex-shrink: 0;
		font-size: 12px;
		height: 24px;
		padding: 0 6px;
		border-radius: 6px;
	}

	&__toolbar {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-shrink: 0;
	}

	&__tool-btn {
		width: 28px;
		height: 28px;
		padding: 0;
		border-radius: 8px;
		font-size: 13px;
	}

	&__sessions {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		padding: 12px 14px 10px;
	}

	&__title {
		font-size: 12px;
		font-weight: 500;
		color: var(--el-text-color-secondary);
		margin-bottom: 10px;
		padding: 0 2px;
		line-height: 1;
	}

	&__list {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding-right: 2px;
	}

	&__empty {
		color: var(--el-text-color-placeholder);
		font-size: 13px;
		text-align: center;
		padding: 32px 0;
	}

	&__collapsed-body {
		padding: 12px 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
	}
}

.collapsed-session-dot {
	width: 34px;
	height: 34px;
	border-radius: 8px;
	background: var(--el-fill-color-light);
	color: var(--el-text-color-secondary);
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 12px;
	font-weight: 600;
	cursor: pointer;
	transition: all 0.2s ease;

	&:hover {
		background: var(--el-color-primary-light-8);
		color: var(--el-color-primary);
	}

	&.active {
		background: var(--el-color-primary);
		color: #fff;
	}
}

.ws-session-item {
	padding: 8px 10px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	background: var(--el-fill-color-blank);
	cursor: pointer;
	display: flex;
	justify-content: space-between;
	align-items: center;
	min-height: 52px;
	box-sizing: border-box;
	transition: all 0.2s ease;
	position: relative;

	&:hover {
		border-color: var(--el-color-primary-light-5);
		background-color: var(--el-fill-color-light);
	}

	&.active {
		border-color: var(--el-color-primary);
		background: linear-gradient(135deg, var(--el-color-primary-light-9), #f0f7ff);

		.ws-session-item__title {
			color: var(--el-color-primary);
			font-weight: 600;
		}
	}

	&__main {
		display: flex;
		flex-direction: column;
		justify-content: center;
		gap: 4px;
		flex: 1;
		min-width: 0;
		padding-right: 6px;
	}

	&__title {
		font-size: 13px;
		line-height: 1.35;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--el-text-color-primary);
	}

	&__time {
		font-size: 11px;
		color: var(--el-text-color-placeholder);
		line-height: 1.2;
	}

	&__actions {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-shrink: 0;

		.action-btn {
			width: 26px;
			height: 26px;
			padding: 0;
			font-size: 12px;
			border-radius: 6px;
		}
	}
}

.ws-main {
	flex: 1;
	display: flex;
	flex-direction: column;
	overflow: hidden;
	background-color: var(--el-bg-color);
}

.ws-topbar {
	display: flex;
	justify-content: space-between;
	align-items: center;
	padding: 10px 18px;
	border-bottom: 1px solid var(--el-border-color-lighter);
	background-color: var(--el-fill-color-blank);

	&__left {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.expand-toggle-btn {
		margin-right: 4px;
	}

	&__icon {
		color: var(--el-color-primary);
		font-size: 18px;
		flex-shrink: 0;
	}

	&__name {
		font-size: 15px;
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	&__status-tag {
		flex-shrink: 0;
	}

	&__session-tag {
		max-width: 220px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		flex-shrink: 0;
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
	padding: 18px;
	display: flex;
	flex-direction: column;

	&__empty {
		color: var(--el-text-color-secondary);
		text-align: center;
		margin-top: 15%;
	}
}

.ws-content-container {
	max-width: 860px;
	margin: auto auto 0;
	width: 100%;

	&:has(.chat-message) {
		margin-top: 0;
	}
}

.ws-analysis {
	margin: 12px 0 16px;
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

.ws-stop-hint {
	margin: 8px 0;
}

.ws-input-wrapper {
	padding: 12px 18px 16px;
	background-color: var(--el-fill-color-blank);
	border-top: 1px solid var(--el-border-color-lighter);
}

.chat-input-card {
	position: relative;
	background: var(--el-fill-color-lighter);
	border: 1px solid var(--el-border-color);
	border-radius: 14px;
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
	transition: all 0.25s ease;

	&:focus-within {
		background: var(--el-fill-color-blank);
		border-color: var(--el-color-primary);
		box-shadow: 0 4px 16px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.16);
	}

	.chat-input-textarea {
		width: 100%;

		:deep(.el-textarea__inner) {
			border: none;
			box-shadow: none;
			background: transparent;
			padding: 10px 76px 10px 14px;
			font-size: 14px;
			line-height: 1.5;
			resize: none;

			&:focus {
				box-shadow: none;
			}
		}
	}

	.inner-send-btn {
		position: absolute;
		right: 8px;
		bottom: 7px;
		height: 30px;
		padding: 0 14px;
		border-radius: 15px;
		font-weight: 500;
		box-shadow: 0 2px 6px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.25);
		transition: all 0.2s;

		&:hover:not(:disabled) {
			transform: translateY(-1px);
			box-shadow: 0 4px 10px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.35);
		}
	}

	.inner-attach-btn {
		position: absolute;
		right: 100px;
		bottom: 7px;
		height: 30px;
		width: 30px;
		padding: 0;
		border-radius: 15px;
	}

	.ws-attach-input {
		display: none;
	}

	.pending-attachments {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		padding: 10px 14px 0;
	}

	.pending-attachment {
		position: relative;
		width: 56px;
		height: 56px;
		border-radius: 8px;
		overflow: visible;

		&__thumb {
			width: 56px;
			height: 56px;
			border-radius: 8px;
			display: block;
			border: 1px solid var(--el-border-color-lighter);
		}

		&__file {
			width: 56px;
			height: 56px;
			border-radius: 8px;
			background: var(--el-fill-color);
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			gap: 2px;
			padding: 4px;
			box-sizing: border-box;

			.el-icon {
				color: var(--el-color-primary);
			}
		}

		&__name {
			font-size: 10px;
			color: var(--el-text-color-secondary);
			max-width: 100%;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}

		&__remove {
			position: absolute;
			top: -6px;
			right: -6px;
			font-size: 16px;
			color: var(--el-text-color-secondary);
			background: var(--el-bg-color);
			border-radius: 50%;
			cursor: pointer;
			z-index: 1;

			&:hover {
				color: var(--el-color-danger);
			}
		}
	}
}
</style>
