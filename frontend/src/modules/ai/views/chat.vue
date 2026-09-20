<template>
	<div class="ai-chat-test">
		<section class="chat-panel">
			<header class="toolbar">
				<cl-select
					v-model="form.profileCode"
					:options="profileOptions"
					:placeholder="$t('默认调用配置')"
					clearable
					:width="260"
				/>

				<el-input v-model="form.scenario" :placeholder="$t('场景')" clearable />

				<el-input-number
					v-model="form.maxTokens"
					:min="16"
					:max="4096"
					:step="64"
					controls-position="right"
				/>
			</header>

			<div ref="messagesContainer" class="messages">
				<div v-for="item in messages" :key="item.id" class="message" :class="item.role">
					<div class="role">{{ item.role === 'user' ? $t('用户') : $t('AI') }}</div>
					<pre>{{ item.content }}</pre>
				</div>
			</div>

			<footer class="composer">
				<cl-editor-markdown v-model="prompt" :height="200" simple />

				<div class="actions">
					<el-button @click="clearAll">{{ $t('清空') }}</el-button>
					<el-button :loading="loading.chat" type="primary" @click="sendChat">{{
						$t('发送')
					}}</el-button>
					<el-button :loading="loading.stream" type="success" @click="sendStream">{{
						$t('流式发送')
					}}</el-button>
					<el-button :disabled="!loading.stream" type="danger" @click="stopStream">{{
						$t('停止')
					}}</el-button>
				</div>
			</footer>
		</section>

		<aside class="stream-panel">
			<header>
				<span>{{ $t('实时流') }}</span>
				<el-tag v-if="streamStatus" size="small" :type="streamStatusType">{{
					streamStatus
				}}</el-tag>
			</header>

			<div class="stream-content">
				<div v-for="(item, index) in streamEvents" :key="index" class="stream-event">
					<span class="event-name">{{ item.event || 'message' }}</span>
					<pre>{{ formatEvent(item) }}</pre>
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

const { service } = useCool();
const { t } = useI18n();
const stream = useStream();

// 组件卸载时取消进行中的 SSE 流：避免连接泄漏与回调向已卸载组件写状态
onBeforeUnmount(() => {
	stream.cancel();
	window.removeEventListener('keydown', onCtrlEnter);
});

const profileOptions = ref<{ label: string; value: string }[]>([]);
const prompt = ref('你好，请用一句话介绍你自己。');
const messages = ref<{ id: number; role: 'user' | 'assistant'; content: string }[]>([]);
const streamEvents = ref<any[]>([]);
const streamStatus = ref('');
const loading = reactive({
	chat: false,
	stream: false
});
const form = reactive({
	profileCode: '',
	scenario: 'default',
	maxTokens: 512
});

const streamStatusType = computed(() => {
	if (streamStatus.value === 'error') {
		return 'danger';
	}
	if (streamStatus.value === 'done') {
		return 'success';
	}
	return 'info';
});

const messagesContainer = ref<HTMLElement>();
// 流式取消标志：stopStream 置 true，使回调中迟到的 error 事件不再误报失败
let streamCancelled = false;

function onCtrlEnter(e: KeyboardEvent) {
	if (e.ctrlKey && e.key === 'Enter') {
		e.preventDefault();
		sendChat();
	}
}

// 新消息加入后平滑滚动到底部
watch(
	() => messages.value.length,
	() => scrollToBottom('smooth')
);

// 流式输出期间节流跟随：仅当用户停留在底部附近时跟进，不打断向上翻阅
let lastFollowAt = 0;

function followStreamOutput() {
	const now = Date.now();
	if (now - lastFollowAt < 100) {
		return;
	}
	lastFollowAt = now;
	scrollToBottom('auto');
}

function scrollToBottom(behavior: ScrollBehavior) {
	nextTick(() => {
		const el = messagesContainer.value;
		if (!el) {
			return;
		}
		if (behavior === 'auto' && el.scrollHeight - el.scrollTop - el.clientHeight > 120) {
			// 用户已向上翻阅，不强制拉回
			return;
		}
		el.scrollTo({ top: el.scrollHeight, behavior });
	});
}

onMounted(() => {
	loadProfiles();
	window.addEventListener('keydown', onCtrlEnter);
});

async function loadProfiles() {
	// EPS 生成的 list 参数类型未含业务查询字段，实际后端支持，此处对参数放宽类型
	const res = await service.ai.profile.list({
		modelType: 'chat',
		status: true
	} as any);
	profileOptions.value = (res || []).map((item: any) => ({
		label: `${item.name || item.code} / ${item.modelName || item.modelId}`,
		value: item.code
	}));
}

function buildPayload() {
	const text = prompt.value.trim();
	if (!text) {
		ElMessage.warning(t('请输入提示词'));
		return null;
	}

	return {
		scenario: form.scenario || 'default',
		profileCode: form.profileCode || undefined,
		messages: [{ role: 'user', content: text }],
		options: {
			max_tokens: form.maxTokens
		}
	};
}

async function sendChat() {
	const payload = buildPayload();
	if (!payload) {
		return;
	}

	loading.chat = true;
	addMessage('user', prompt.value.trim());

	try {
		const res = await aiRuntime.chat(payload);
		addMessage('assistant', res?.content || JSON.stringify(res, null, 2));
	} catch (err: any) {
		ElMessage.error(err.message || t('调用失败'));
	} finally {
		loading.chat = false;
	}
}

async function sendStream() {
	const payload = buildPayload();
	if (!payload) {
		return;
	}

	streamCancelled = false;
	loading.stream = true;
	streamStatus.value = 'start';
	streamEvents.value = [];
	addMessage('user', prompt.value.trim());

	// 先压入空的 assistant 占位气泡，流式期间增量填充，避免"生成中无反馈"
	const assistantMsg = reactive({
		id: Date.now() + Math.random(),
		role: 'assistant' as const,
		content: ''
	});
	messages.value.push(assistantMsg);

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
						// 全程无内容：移除空气泡，用结束事件兜底展示
						removeMessage(assistantMsg.id);
						addMessage('assistant', JSON.stringify(event, null, 2));
					}
					loading.stream = false;
				}

				if (event.event === 'error') {
					if (streamCancelled) return;
					ElMessage.error(event.message || t('流式调用失败'));
					if (!content) {
						removeMessage(assistantMsg.id);
					}
					loading.stream = false;
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
		streamStatus.value = err.name === 'AbortError' ? 'aborted' : 'error';
	}
}

function stopStream() {
	streamCancelled = true;
	stream.cancel();
	loading.stream = false;
	streamStatus.value = 'aborted';
}

function clearAll() {
	messages.value = [];
	streamEvents.value = [];
	streamStatus.value = '';
}

function addMessage(role: 'user' | 'assistant', content: string) {
	messages.value.push({
		id: Date.now() + Math.random(),
		role,
		content
	});
}

function removeMessage(id: number) {
	const index = messages.value.findIndex(item => item.id === id);
	if (index !== -1) {
		messages.value.splice(index, 1);
	}
}

function formatEvent(event: any) {
	return JSON.stringify(event, null, 2);
}
</script>

<style lang="scss" scoped>
.ai-chat-test {
	display: grid;
	grid-template-columns: minmax(0, 1fr) 360px;
	gap: 12px;
	height: 100%;
	min-height: 640px;
}

.chat-panel,
.stream-panel {
	display: flex;
	min-height: 0;
	border: 1px solid var(--el-border-color-light);
	background: var(--el-bg-color);
}

.chat-panel {
	flex-direction: column;
}

.toolbar {
	display: grid;
	grid-template-columns: 260px minmax(140px, 1fr) 140px;
	gap: 10px;
	padding: 12px;
	border-bottom: 1px solid var(--el-border-color-light);
}

.messages,
.stream-content {
	flex: 1;
	min-height: 0;
	overflow: auto;
	padding: 12px;
}

.message {
	max-width: 78%;
	margin-bottom: 12px;
	padding: 10px 12px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-lighter);

	&.user {
		margin-left: auto;
		background: var(--el-color-primary-light-9);
	}

	.role {
		margin-bottom: 6px;
		font-size: 12px;
		color: var(--el-text-color-secondary);
	}

	pre {
		margin: 0;
		white-space: pre-wrap;
		word-break: break-word;
		font-family: inherit;
	}
}

.composer {
	padding: 12px;
	border-top: 1px solid var(--el-border-color-light);

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 10px;
	}
}

.stream-panel {
	flex-direction: column;

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px;
		border-bottom: 1px solid var(--el-border-color-light);
		font-weight: 600;
	}
}

.stream-event {
	margin-bottom: 10px;
	padding: 8px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-blank);

	.event-name {
		display: inline-block;
		margin-bottom: 6px;
		font-size: 12px;
		font-weight: 600;
		color: var(--el-color-primary);
	}

	pre {
		margin: 0;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 12px;
	}
}

@media (max-width: 960px) {
	.ai-chat-test {
		grid-template-columns: 1fr;
		height: auto;
	}

	.toolbar {
		grid-template-columns: 1fr;
	}
}
</style>
