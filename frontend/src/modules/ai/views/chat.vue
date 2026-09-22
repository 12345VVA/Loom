<template>
	<div class="ai-chat-workbench" :class="{ 'with-stream-open': showStreamDrawer }">
		<!-- 主对话工作区 -->
		<section class="chat-container">
			<!-- 顶部工具栏 -->
			<header class="chat-header">
				<div class="header-left">
					<div class="title-badge">
						<el-icon class="title-icon"><chat-dot-round /></el-icon>
						<span class="title-text">{{ $t('对话测试') }}</span>
					</div>

					<cl-select
						v-model="form.profileCode"
						:options="profileOptions"
						:placeholder="$t('默认调用配置')"
						clearable
						:width="220"
					/>

					<el-input
						v-model="form.scenario"
						:placeholder="$t('场景 (如 default)')"
						clearable
						style="width: 140px"
					/>
				</div>

				<div class="header-right">
					<!-- 高级参数设置 Popover -->
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
									:min="16"
									:max="8192"
									:step="128"
									controls-position="right"
									style="width: 100%"
								/>
							</div>

							<div class="param-item">
								<div class="param-header">
									<span>System Prompt ({{ $t('系统提示词') }}):</span>
								</div>
								<el-input
									v-model="form.systemPrompt"
									type="textarea"
									:rows="3"
									resize="none"
									:placeholder="$t('为 AI 设定人设或背景约束，如：你是一名专业的资深架构师...')"
								/>
							</div>
						</div>
					</el-popover>

					<!-- 携带历史上下文开关 -->
					<el-tooltip
						:content="$t('开启后将携带历史多轮对话上下文连续交互；关闭则只发送当前单条')"
						placement="bottom"
					>
						<div class="context-switch">
							<span class="switch-label">{{ $t('连续上下文') }}</span>
							<el-switch v-model="form.carryContext" size="small" />
						</div>
					</el-tooltip>

					<!-- 清空会话 -->
					<el-tooltip :content="$t('清空对话消息')" placement="bottom">
						<el-button link size="small" @click="clearAll">
							<el-icon><delete /></el-icon>
						</el-button>
					</el-tooltip>

					<el-divider direction="vertical" />

					<!-- 实时流调试开关按钮 -->
					<el-button
						:type="showStreamDrawer ? 'primary' : 'default'"
						plain
						size="small"
						class="stream-toggle-btn"
						@click="toggleStreamDrawer"
					>
						<el-icon class="mr-2"><data-analysis /></el-icon>
						<span>{{ $t('实时流') }}</span>
						<span v-if="streamEvents.length" class="stream-count-badge">
							{{ streamEvents.length }}
						</span>
					</el-button>
				</div>
			</header>

			<!-- 消息历史滚动区 -->
			<div ref="messagesContainer" class="messages-flow">
				<!-- 空状态：欢迎卡片与灵感卡片 -->
				<div v-if="!messages.length" class="empty-chat-welcome">
					<div class="welcome-avatar">
						<el-icon><magic-stick /></el-icon>
					</div>
					<h2 class="welcome-title">{{ $t('开启 AI 智能对话') }}</h2>
					<p class="welcome-desc">
						{{ $t('已就绪！在下方输入您的问题或指令，支持流式实时打字与 Markdown 富文本排版。') }}
					</p>

					<div class="sample-prompts-grid">
						<div
							v-for="(item, idx) in SAMPLE_QUESTIONS"
							:key="idx"
							class="sample-card"
							@click="useSamplePrompt(item.prompt)"
						>
							<div class="sample-icon">
								<component :is="item.icon" />
							</div>
							<div class="sample-content">
								<div class="sample-title">{{ item.title }}</div>
								<div class="sample-sub">{{ item.prompt }}</div>
							</div>
						</div>
					</div>
				</div>

				<!-- 消息气泡流 -->
				<div
					v-for="item in messages"
					:key="item.id"
					class="message-row"
					:class="item.role"
				>
					<!-- 头像 -->
					<div class="message-avatar">
						<el-icon v-if="item.role === 'user'"><user /></el-icon>
						<el-icon v-else class="ai-avatar-icon"><magic-stick /></el-icon>
					</div>

					<!-- 气泡内容 -->
					<div class="message-bubble-wrapper">
						<div class="message-header-info">
							<span class="role-name">{{ item.role === 'user' ? $t('我') : $t('AI 助手') }}</span>
							<span v-if="item.time" class="time-label">{{ item.time }}</span>
						</div>

						<div class="message-bubble">
							<!-- 用户气泡：纯文本保留换行 -->
							<div v-if="item.role === 'user'" class="user-text">
								{{ item.content }}
							</div>

							<!-- AI 气泡：Markdown 渲染 -->
							<div v-else class="assistant-content">
								<div
									v-if="item.content"
									class="markdown-body"
									v-html="renderMarkdown(item.content)"
								></div>
								<div v-else-if="loading.stream || loading.chat" class="typing-placeholder">
									<span class="typing-dot"></span>
									<span class="typing-dot"></span>
									<span class="typing-dot"></span>
								</div>
								<span
									v-if="isStreamingCurrent(item.id)"
									class="typing-cursor"
								></span>
							</div>
						</div>

						<!-- 气泡悬浮操作工具条 -->
						<div class="message-actions">
							<button
								type="button"
								class="bubble-action-btn"
								:title="$t('复制内容')"
								@click="copyText(item.content)"
							>
								<el-icon><copy-document /></el-icon>
							</button>

							<button
								v-if="item.role === 'assistant' && !isStreamingCurrent(item.id)"
								type="button"
								class="bubble-action-btn"
								:title="$t('重新生成')"
								@click="regenerateFrom(item.id)"
							>
								<el-icon><refresh /></el-icon>
							</button>

							<button
								type="button"
								class="bubble-action-btn"
								:title="$t('删除此条')"
								@click="removeMessage(item.id)"
							>
								<el-icon><delete /></el-icon>
							</button>
						</div>
					</div>
				</div>
			</div>

			<!-- 底部紧凑输入栏 -->
			<footer class="composer-container">
				<div class="composer-box">
					<el-input
						ref="promptInputRef"
						v-model="prompt"
						type="textarea"
						:autosize="{ minRows: 2, maxRows: 6 }"
						resize="none"
						class="chat-input"
						:placeholder="$t('输入您的问题，按 Enter 发送，Shift + Enter 换行...')"
						@keydown="handleInputKeydown"
					/>

					<div class="composer-bar">
						<div class="bar-left">
							<span class="key-hint">{{ $t('Enter 发送 / Shift + Enter 换行') }}</span>
						</div>

						<div class="bar-right">
							<el-button link size="small" @click="prompt = ''">
								{{ $t('清空输入') }}
							</el-button>

							<!-- 普通发送 -->
							<el-button
								v-if="!isBusy"
								size="default"
								plain
								:loading="loading.chat"
								@click="sendChat"
							>
								{{ $t('普通发送') }}
							</el-button>

							<!-- 流式发送 / 停止生成 -->
							<el-button
								v-if="loading.stream"
								type="danger"
								size="default"
								class="action-main-btn"
								@click="stopStream"
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
								@click="sendStream"
							>
								<el-icon class="mr-2"><promotion /></el-icon>
								{{ $t('流式发送') }}
							</el-button>
						</div>
					</div>
				</div>
			</footer>
		</section>

		<!-- 右侧：实时流调试侧边抽屉 -->
		<aside v-if="showStreamDrawer" class="stream-drawer">
			<header class="stream-header">
				<div class="stream-title-group">
					<el-icon class="stream-icon"><data-analysis /></el-icon>
					<strong>{{ $t('SSE 实时流审计') }}</strong>
					<el-tag v-if="streamStatus" size="small" :type="streamStatusType">
						{{ streamStatus }}
					</el-tag>
				</div>
				<div class="stream-header-tools">
					<el-button link size="small" @click="clearStreamLogs">
						{{ $t('清空') }}
					</el-button>
					<el-button link size="small" @click="copyStreamLogs">
						{{ $t('复制全部') }}
					</el-button>
					<el-icon class="drawer-close" @click="showStreamDrawer = false">
						<close />
					</el-icon>
				</div>
			</header>

			<div class="stream-list">
				<div
					v-for="(item, index) in streamEvents"
					:key="index"
					class="stream-event-card"
					:class="item.event"
				>
					<div class="event-meta">
						<span class="event-tag">{{ item.event || 'message' }}</span>
						<span class="event-seq">#{{ index + 1 }}</span>
					</div>
					<pre class="event-body">{{ formatEvent(item) }}</pre>
				</div>

				<div v-if="!streamEvents.length" class="empty-stream">
					<el-icon><connection /></el-icon>
					<span>{{ $t('暂无实时流事件') }}</span>
					<p>{{ $t('使用「流式发送」时，后端分块事件将实时在此展示') }}</p>
				</div>
			</div>
		</aside>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-chat'
});

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { useStream } from '/@/cool/service/stream';
import { aiRuntime } from '/$/ai';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import {
	ChatDotRound,
	Operation,
	Delete,
	DataAnalysis,
	MagicStick,
	User,
	CopyDocument,
	Refresh,
	Promotion,
	VideoPause,
	Close,
	Connection,
	Edit,
	Document,
	Reading,
	Search
} from '@element-plus/icons-vue';

const { service } = useCool();
const { t } = useI18n();
const stream = useStream();

// Markdown 配置
marked.setOptions({
	gfm: true,
	breaks: true
});

function renderMarkdown(content: string): string {
	if (!content) return '';
	try {
		const raw = marked.parse(content, { async: false }) as string;
		return DOMPurify.sanitize(raw);
	} catch (e) {
		return content;
	}
}

// 状态管理
const profileOptions = ref<{ label: string; value: string }[]>([]);
const prompt = ref('');
const promptInputRef = ref();

interface ChatMessageItem {
	id: number;
	role: 'user' | 'assistant';
	content: string;
	time?: string;
}

const messages = ref<ChatMessageItem[]>([]);
const streamEvents = ref<any[]>([]);
const streamStatus = ref('');
const showStreamDrawer = ref(false);

const loading = reactive({
	chat: false,
	stream: false
});

const isBusy = computed(() => loading.chat || loading.stream);

const form = reactive({
	profileCode: '',
	scenario: 'default',
	maxTokens: 1024,
	temperature: 0.7,
	systemPrompt: '',
	carryContext: true
});

const currentStreamingId = ref<number | null>(null);

function isStreamingCurrent(id: number): boolean {
	return loading.stream && currentStreamingId.value === id;
}

const streamStatusType = computed(() => {
	if (streamStatus.value === 'error') return 'danger';
	if (streamStatus.value === 'done') return 'success';
	if (streamStatus.value === 'start' || streamStatus.value === 'delta') return 'primary';
	return 'info';
});

const messagesContainer = ref<HTMLElement>();
let streamCancelled = false;

// 常用灵感问题
const SAMPLE_QUESTIONS = [
	{
		title: '编写快速排序算法',
		prompt: '请用 Python 编写一个快速排序算法，并分析其时间与空间复杂度。',
		icon: Document
	},
	{
		title: '通俗解释量子纠缠',
		prompt: '请用通俗易懂的生活化比喻，向高中生解释什么是量子纠缠现象。',
		icon: Reading
	},
	{
		title: '架构设计原则',
		prompt: '在设计高并发分布式系统时，有哪些核心的设计原则和容灾方案？',
		icon: Edit
	},
	{
		title: '英文商务邮件润色',
		prompt: '帮我润色一封写给海外客户的软件项目交付验收邮件，语气专业得体。',
		icon: Search
	}
];

function useSamplePrompt(text: string) {
	prompt.value = text;
	nextTick(() => {
		promptInputRef.value?.focus();
	});
}

function toggleStreamDrawer() {
	showStreamDrawer.value = !showStreamDrawer.value;
}

// 键盘快捷键响应：Enter 发送，Shift+Enter 换行
function handleInputKeydown(e: KeyboardEvent | Event) {
	if ('key' in e && e.key === 'Enter' && !e.shiftKey) {
		e.preventDefault();
		if (!isBusy.value) {
			sendStream();
		}
	}
}

// 消息滚动跟随
let lastFollowAt = 0;
function followStreamOutput() {
	const now = Date.now();
	if (now - lastFollowAt < 80) return;
	lastFollowAt = now;
	scrollToBottom('auto');
}

function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
	nextTick(() => {
		const el = messagesContainer.value;
		if (!el) return;
		if (behavior === 'auto' && el.scrollHeight - el.scrollTop - el.clientHeight > 150) {
			// 用户向上翻阅中，不强行吸底
			return;
		}
		el.scrollTo({ top: el.scrollHeight, behavior });
	});
}

watch(
	() => messages.value.length,
	() => scrollToBottom('smooth')
);

onMounted(() => {
	loadProfiles();
});

onBeforeUnmount(() => {
	stream.cancel();
});

async function loadProfiles() {
	try {
		const res = await service.ai.profile.list({
			modelType: 'chat',
			status: true
		} as any);
		profileOptions.value = (res || []).map((item: any) => ({
			label: `${item.name || item.code} / ${item.modelName || item.modelId}`,
			value: item.code
		}));
	} catch (e) {
		console.warn('加载 profile 列表失败:', e);
	}
}

function formatCurrentTime() {
	const now = new Date();
	return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
}

// 构建上下文 Payload
function buildPayload(newText: string) {
	const text = newText.trim();
	if (!text) {
		ElMessage.warning(t('请输入您的问题'));
		return null;
	}

	const history: { role: string; content: string }[] = [];

	// 1. 系统提示词
	if (form.systemPrompt && form.systemPrompt.trim()) {
		history.push({ role: 'system', content: form.systemPrompt.trim() });
	}

	// 2. 多轮历史消息
	if (form.carryContext) {
		for (const msg of messages.value) {
			if (msg.content) {
				history.push({ role: msg.role, content: msg.content });
			}
		}
	}

	// 3. 当前输入
	history.push({ role: 'user', content: text });

	return {
		scenario: form.scenario || 'default',
		profileCode: form.profileCode || undefined,
		messages: history,
		options: {
			max_tokens: form.maxTokens,
			temperature: form.temperature
		}
	};
}

// 普通请求
async function sendChat() {
	const text = prompt.value.trim();
	const payload = buildPayload(text);
	if (!payload) return;

	loading.chat = true;
	addMessage('user', text);
	prompt.value = '';

	try {
		const res = await aiRuntime.chat(payload);
		addMessage('assistant', res?.content || JSON.stringify(res, null, 2));
	} catch (err: any) {
		ElMessage.error(err.message || t('调用失败'));
	} finally {
		loading.chat = false;
	}
}

// 流式请求
async function sendStream() {
	const text = prompt.value.trim();
	const payload = buildPayload(text);
	if (!payload) return;

	streamCancelled = false;
	loading.stream = true;
	streamStatus.value = 'start';
	streamEvents.value = [];
	addMessage('user', text);
	prompt.value = '';

	const assistantMsg = reactive<ChatMessageItem>({
		id: Date.now() + Math.random(),
		role: 'assistant',
		content: '',
		time: formatCurrentTime()
	});
	messages.value.push(assistantMsg);
	currentStreamingId.value = assistantMsg.id;

	let content = '';

	try {
		await stream.invoke({
			url: aiRuntime.streamUrl(),
			data: payload,
			cb(event) {
				streamEvents.value.push(event);
				streamStatus.value = event.event || 'message';

				if (event.event === 'delta') {
					content += event.content || '';
					assistantMsg.content = content;
					followStreamOutput();
				}

				if (event.event === 'done') {
					if (!content && event.content) {
						content = event.content;
						assistantMsg.content = content;
					}
					if (!content) {
						removeMessage(assistantMsg.id);
						addMessage('assistant', JSON.stringify(event, null, 2));
					}
					loading.stream = false;
					currentStreamingId.value = null;
				}

				if (event.event === 'error') {
					if (streamCancelled) return;
					ElMessage.error(event.message || t('流式调用失败'));
					if (!content) {
						removeMessage(assistantMsg.id);
					}
					loading.stream = false;
					currentStreamingId.value = null;
				}
			}
		});
	} catch (err: any) {
		if (err.name !== 'AbortError') {
			ElMessage.error(err.message || t('流式调用失败'));
		}
		if (!content) {
			removeMessage(assistantMsg.id);
		}
		loading.stream = false;
		currentStreamingId.value = null;
		streamStatus.value = err.name === 'AbortError' ? 'aborted' : 'error';
	}
}

function stopStream() {
	streamCancelled = true;
	stream.cancel();
	loading.stream = false;
	currentStreamingId.value = null;
	streamStatus.value = 'aborted';
	ElMessage.info(t('已停止生成'));
}

// 针对指定 AI 消息重新生成
function regenerateFrom(msgId: number) {
	if (isBusy.value) return;
	const index = messages.value.findIndex(m => m.id === msgId);
	if (index === -1) return;

	// 找到该 AI 消息前最近的一条 user 提问及其索引
	let userIndex = -1;
	for (let i = index - 1; i >= 0; i--) {
		if (messages.value[i].role === 'user') {
			userIndex = i;
			break;
		}
	}
	if (userIndex === -1) return;

	const userPrompt = messages.value[userIndex].content;
	if (!userPrompt) return;

	// 截断：移除该 user 提问及后续所有消息，由 sendStream 重新发送并流式输出
	messages.value.splice(userIndex);
	prompt.value = userPrompt;
	sendStream();
}

function clearAll() {
	messages.value = [];
	streamEvents.value = [];
	streamStatus.value = '';
	ElMessage.success(t('已清空对话'));
}

function addMessage(role: 'user' | 'assistant', content: string) {
	messages.value.push({
		id: Date.now() + Math.random(),
		role,
		content,
		time: formatCurrentTime()
	});
}

function removeMessage(id: number) {
	const index = messages.value.findIndex(item => item.id === id);
	if (index !== -1) {
		messages.value.splice(index, 1);
	}
}

async function copyText(value: string) {
	if (!value) return;
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制内容'));
}

function clearStreamLogs() {
	streamEvents.value = [];
	ElMessage.success(t('已清空实时流日志'));
}

async function copyStreamLogs() {
	if (!streamEvents.value.length) return;
	await navigator.clipboard.writeText(JSON.stringify(streamEvents.value, null, 2));
	ElMessage.success(t('已复制全部实时流日志'));
}

function formatEvent(event: any) {
	return JSON.stringify(event, null, 2);
}
</script>

<style lang="scss" scoped>
.ai-chat-workbench {
	display: flex;
	height: calc(100vh - 110px);
	min-height: 640px;
	box-sizing: border-box;
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	overflow: hidden;
	position: relative;
}

/* ================== 主对话区域 ================== */
.chat-container {
	flex: 1;
	display: flex;
	flex-direction: column;
	min-width: 0;
	height: 100%;
}

/* 顶部工具栏 */
.chat-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 10px 16px;
	background: var(--el-fill-color-blank);
	border-bottom: 1px solid var(--el-border-color-lighter);
	flex-shrink: 0;

	.header-left {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;

		.title-badge {
			display: flex;
			align-items: center;
			gap: 6px;
			margin-right: 4px;

			.title-icon {
				font-size: 18px;
				color: var(--el-color-primary);
			}

			.title-text {
				font-size: 15px;
				font-weight: 650;
				color: var(--el-text-color-primary);
			}
		}
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 8px;

		.context-switch {
			display: flex;
			align-items: center;
			gap: 6px;
			padding: 4px 8px;
			background: var(--el-fill-color-light);
			border-radius: 4px;

			.switch-label {
				font-size: 12px;
				color: var(--el-text-color-regular);
			}
		}

		.stream-toggle-btn {
			position: relative;
			.stream-count-badge {
				margin-left: 4px;
				padding: 0 5px;
				font-size: 11px;
				background: var(--el-color-primary-light-8);
				color: var(--el-color-primary);
				border-radius: 8px;
			}
		}
	}
}

/* 推理参数 Popover */
.params-popover {
	display: flex;
	flex-direction: column;
	gap: 12px;

	.popover-title {
		font-size: 13px;
		font-weight: 650;
		color: var(--el-text-color-primary);
		padding-bottom: 6px;
		border-bottom: 1px solid var(--el-border-color-lighter);
	}

	.param-item {
		display: flex;
		flex-direction: column;
		gap: 4px;

		.param-header {
			display: flex;
			justify-content: space-between;
			font-size: 12px;
			color: var(--el-text-color-regular);

			.param-val {
				font-weight: 600;
				color: var(--el-color-primary);
			}
		}
	}
}

/* ================== 消息流滚动区 ================== */
.messages-flow {
	flex: 1;
	min-height: 0;
	overflow-y: auto;
	padding: 20px 24px;
	display: flex;
	flex-direction: column;
	gap: 18px;

	&::-webkit-scrollbar {
		width: 6px;
	}
	&::-webkit-scrollbar-thumb {
		background: var(--el-border-color-light);
		border-radius: 3px;
	}
}

/* 空状态欢迎卡片 */
.empty-chat-welcome {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	margin: auto 0;
	padding: 30px 20px;
	text-align: center;

	.welcome-avatar {
		width: 56px;
		height: 56px;
		border-radius: 50%;
		background: linear-gradient(135deg, var(--el-color-primary-light-8), var(--el-color-primary-light-9));
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 26px;
		color: var(--el-color-primary);
		margin-bottom: 12px;
		box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
	}

	.welcome-title {
		font-size: 18px;
		font-weight: 650;
		color: var(--el-text-color-primary);
		margin: 0 0 6px;
	}

	.welcome-desc {
		font-size: 13px;
		color: var(--el-text-color-secondary);
		margin: 0 0 24px;
		max-width: 440px;
		line-height: 1.5;
	}

	.sample-prompts-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(220px, 300px));
		gap: 10px;
		width: 100%;
		max-width: 620px;
	}

	.sample-card {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		padding: 12px;
		background: var(--el-fill-color-blank);
		border: 1px solid var(--el-border-color-light);
		border-radius: 8px;
		cursor: pointer;
		text-align: left;
		transition: all 0.2s ease;

		&:hover {
			border-color: var(--el-color-primary);
			box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
			transform: translateY(-2px);
		}

		.sample-icon {
			font-size: 18px;
			color: var(--el-color-primary);
			margin-top: 2px;
			flex-shrink: 0;
		}

		.sample-title {
			font-size: 13px;
			font-weight: 600;
			color: var(--el-text-color-primary);
			margin-bottom: 3px;
		}

		.sample-sub {
			font-size: 11px;
			color: var(--el-text-color-secondary);
			line-height: 1.4;
			display: -webkit-box;
			-webkit-line-clamp: 2;
			-webkit-box-orient: vertical;
			overflow: hidden;
		}
	}
}

/* 消息行 */
.message-row {
	display: flex;
	gap: 12px;
	max-width: 860px;
	width: 100%;
	margin: 0 auto;

	.message-avatar {
		width: 34px;
		height: 34px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		font-size: 16px;
	}

	.message-bubble-wrapper {
		display: flex;
		flex-direction: column;
		max-width: calc(100% - 48px);

		.message-header-info {
			display: flex;
			align-items: center;
			gap: 8px;
			margin-bottom: 4px;
			font-size: 11px;
			color: var(--el-text-color-placeholder);
		}
	}

	/* 用户消息：靠右 */
	&.user {
		flex-direction: row-reverse;

		.message-avatar {
			background: var(--el-color-primary);
			color: #fff;
		}

		.message-bubble-wrapper {
			align-items: flex-end;
		}

		.message-bubble {
			background: var(--el-color-primary);
			color: #fff;
			border-radius: 12px 2px 12px 12px;
			padding: 10px 14px;
			box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);

			.user-text {
				white-space: pre-wrap;
				word-break: break-word;
				font-size: 13px;
				line-height: 1.6;
			}
		}
	}

	/* AI 消息：靠左 */
	&.assistant {
		flex-direction: row;

		.message-avatar {
			background: linear-gradient(135deg, #10b981 0%, #059669 100%);
			color: #fff;
		}

		.message-bubble-wrapper {
			align-items: flex-start;
		}

		.message-bubble {
			background: var(--el-fill-color-light);
			border: 1px solid var(--el-border-color-lighter);
			border-radius: 2px 12px 12px 12px;
			padding: 12px 16px;
			box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
			width: 100%;
			box-sizing: border-box;

			.assistant-content {
				position: relative;
				font-size: 13px;
				line-height: 1.7;
				color: var(--el-text-color-primary);
				word-break: break-word;
			}
		}
	}

	/* 悬浮操作小工具条 */
	.message-actions {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 4px;
		opacity: 0;
		transition: opacity 0.2s ease;

		.bubble-action-btn {
			width: 24px;
			height: 24px;
			border-radius: 4px;
			background: var(--el-fill-color-light);
			border: 1px solid var(--el-border-color-lighter);
			color: var(--el-text-color-regular);
			display: flex;
			align-items: center;
			justify-content: center;
			cursor: pointer;
			font-size: 12px;
			transition: all 0.2s;

			&:hover {
				color: var(--el-color-primary);
				border-color: var(--el-color-primary);
			}
		}
	}

	&:hover {
		.message-actions {
			opacity: 1;
		}
	}
}

/* Markdown 渲染样式优化 */
:deep(.markdown-body) {
	p {
		margin: 0 0 8px;
		&:last-child {
			margin-bottom: 0;
		}
	}

	pre {
		background: #1e1e2e;
		color: #e2e8f0;
		padding: 12px;
		border-radius: 6px;
		overflow-x: auto;
		font-family: Consolas, Monaco, monospace;
		font-size: 12px;
		line-height: 1.5;
		margin: 8px 0;
	}

	code {
		font-family: Consolas, Monaco, monospace;
		background: var(--el-fill-color-darker);
		padding: 2px 5px;
		border-radius: 4px;
		font-size: 12px;
	}

	pre code {
		background: transparent;
		padding: 0;
	}

	ul,
	ol {
		padding-left: 20px;
		margin: 6px 0;
	}

	table {
		border-collapse: collapse;
		width: 100%;
		margin: 8px 0;
		font-size: 12px;

		th,
		td {
			border: 1px solid var(--el-border-color);
			padding: 6px 10px;
		}
		th {
			background: var(--el-fill-color-darker);
		}
	}

	blockquote {
		border-left: 3px solid var(--el-color-primary);
		padding-left: 10px;
		margin: 6px 0;
		color: var(--el-text-color-secondary);
	}
}

/* 打字机光标动画 */
.typing-cursor {
	display: inline-block;
	width: 6px;
	height: 14px;
	vertical-align: middle;
	background: var(--el-color-primary);
	margin-left: 3px;
	animation: cursor-blink 0.8s infinite;
}

@keyframes cursor-blink {
	0%,
	100% {
		opacity: 1;
	}
	50% {
		opacity: 0;
	}
}

/* 加载三点波纹 */
.typing-placeholder {
	display: flex;
	align-items: center;
	gap: 4px;
	padding: 4px 0;

	.typing-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--el-color-primary);
		animation: typing-dot 1.2s infinite ease-in-out;

		&:nth-child(2) {
			animation-delay: 0.2s;
		}
		&:nth-child(3) {
			animation-delay: 0.4s;
		}
	}
}

@keyframes typing-dot {
	0%,
	80%,
	100% {
		transform: scale(0.6);
		opacity: 0.4;
	}
	40% {
		transform: scale(1.1);
		opacity: 1;
	}
}

/* ================== 底部紧凑输入栏 ================== */
.composer-container {
	padding: 12px 24px 16px;
	background: var(--el-fill-color-blank);
	border-top: 1px solid var(--el-border-color-lighter);
	flex-shrink: 0;

	.composer-box {
		max-width: 860px;
		margin: 0 auto;
		border: 1px solid var(--el-border-color-light);
		border-radius: 8px;
		overflow: hidden;
		transition: all 0.2s ease;
		background: var(--el-bg-color);

		&:focus-within {
			border-color: var(--el-color-primary);
			box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
		}
	}

	.chat-input {
		:deep(textarea) {
			border: none !important;
			box-shadow: none !important;
			padding: 10px 14px;
			font-size: 13px;
			line-height: 1.6;
			background: transparent;
		}
	}

	.composer-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 6px 12px;
		background: var(--el-fill-color-light);
		border-top: 1px solid var(--el-border-color-lighter);

		.bar-left {
			.key-hint {
				font-size: 11px;
				color: var(--el-text-color-placeholder);
			}
		}

		.bar-right {
			display: flex;
			align-items: center;
			gap: 8px;

			.stream-btn {
				background: linear-gradient(135deg, var(--el-color-primary) 0%, #3b82f6 100%);
				font-weight: 600;
			}
		}
	}
}

/* ================== 右侧实时流调试抽屉 ================== */
.stream-drawer {
	width: 380px;
	border-left: 1px solid var(--el-border-color-light);
	background: var(--el-bg-color);
	display: flex;
	flex-direction: column;
	flex-shrink: 0;
	transition: all 0.3s ease;

	.stream-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 14px;
		border-bottom: 1px solid var(--el-border-color-lighter);
		background: var(--el-fill-color-blank);

		.stream-title-group {
			display: flex;
			align-items: center;
			gap: 6px;
			font-size: 13px;

			.stream-icon {
				color: var(--el-color-primary);
			}
		}

		.stream-header-tools {
			display: flex;
			align-items: center;
			gap: 8px;

			.drawer-close {
				font-size: 14px;
				cursor: pointer;
				color: var(--el-text-color-secondary);
				margin-left: 4px;
				&:hover {
					color: var(--el-color-danger);
				}
			}
		}
	}

	.stream-list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 10px;

		&::-webkit-scrollbar {
			width: 5px;
		}
		&::-webkit-scrollbar-thumb {
			background: var(--el-border-color-light);
			border-radius: 2px;
		}
	}

	.stream-event-card {
		padding: 8px 10px;
		border: 1px solid var(--el-border-color-lighter);
		border-radius: 6px;
		background: var(--el-fill-color-light);

		.event-meta {
			display: flex;
			align-items: center;
			justify-content: space-between;
			margin-bottom: 6px;

			.event-tag {
				font-size: 11px;
				font-weight: 600;
				color: var(--el-color-primary);
			}

			.event-seq {
				font-size: 10px;
				color: var(--el-text-color-placeholder);
			}
		}

		.event-body {
			margin: 0;
			font-family: Consolas, Monaco, monospace;
			font-size: 11px;
			color: var(--el-text-color-primary);
			white-space: pre-wrap;
			word-break: break-all;
			max-height: 180px;
			overflow-y: auto;
		}

		&.error {
			border-color: var(--el-color-danger-light-5);
			background: var(--el-color-danger-light-9);
			.event-tag {
				color: var(--el-color-danger);
			}
		}
		&.done {
			border-color: var(--el-color-success-light-5);
			background: var(--el-color-success-light-9);
			.event-tag {
				color: var(--el-color-success);
			}
		}
	}

	.empty-stream {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 240px;
		color: var(--el-text-color-placeholder);
		font-size: 13px;
		text-align: center;
		gap: 6px;

		.el-icon {
			font-size: 28px;
		}

		p {
			margin: 0;
			font-size: 11px;
			color: var(--el-text-color-secondary);
			max-width: 220px;
		}
	}
}

@media (max-width: 960px) {
	.ai-chat-workbench {
		flex-direction: column;
		height: auto;
	}
	.stream-drawer {
		width: 100%;
		height: 360px;
		border-left: none;
		border-top: 1px solid var(--el-border-color-light);
	}
}
</style>
