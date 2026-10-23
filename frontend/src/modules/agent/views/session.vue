<template>
	<cl-crud ref="Crud">
		<div class="agent-session-page">
			<!-- 左侧：智能体选择 + 会话列表 -->
			<aside class="side-panel">
				<div class="side-section">
					<div class="side-title">{{ t('agent.session.selectProfile') }}</div>
					<el-select
						v-model="currentProfileId"
						:placeholder="t('agent.session.profilePlaceholder')"
						class="profile-select"
					>
						<el-option
							v-for="item in publishedProfiles"
							:key="item.id"
							:label="item.name"
							:value="item.id"
						/>
					</el-select>
				</div>

				<div class="side-section">
					<div class="side-title">
						{{ t('agent.session.history') }}
						<el-button link type="primary" size="small" @click="newSession()">
							{{ t('agent.session.new') }}
						</el-button>
					</div>
					<div class="session-list">
						<div
							v-for="row in sessions"
							:key="row.id"
							class="session-item"
							:class="{ active: row.id === currentSessionId }"
							@click="openSession(row)"
						>
							<span class="session-title">{{ row.title || row.sessionCode }}</span>
							<span class="session-time">{{ formatTime(row.lastMessageAt || row.createTime) }}</span>
						</div>
						<div v-if="!sessions.length" class="session-empty">{{ t('agent.session.empty') }}</div>
					</div>
				</div>
			</aside>

			<!-- 右侧：消息流 + 输入区 -->
			<main class="chat-panel">
				<div ref="messageListRef" class="message-list">
					<div v-if="!messages.length && !running" class="chat-placeholder">
						{{ t('agent.session.placeholder') }}
					</div>
					<ChatMessage v-for="(m, i) in messages" :key="m.id || i" :message="m" />
					<!-- 流式过程中的工具块实时渲染 -->
					<div v-if="runningTool" class="live-tool">
						<el-icon class="is-loading"><Loading /></el-icon>
						{{ t('agent.session.toolRunning') }}：{{ runningTool.toolName }}
					</div>
					<div v-if="running && streamingText" class="bubble assistant-bubble streaming">
						{{ streamingText }}
					</div>
					<el-alert v-if="stopHint" :title="stopHint" type="warning" :closable="false" class="stop-hint" />
				</div>

				<div class="input-area">
					<el-input
						v-model="input"
						type="textarea"
						:rows="3"
						:disabled="running || !currentProfileId"
						:placeholder="t('agent.session.inputPlaceholder')"
						@keydown.ctrl.enter="onSend"
					/>
					<div class="input-actions">
						<span class="hint">{{ t('agent.session.sendHint') }}</span>
						<el-button v-if="running" type="danger" @click="stop()">
							{{ t('agent.session.stop') }}
						</el-button>
						<el-button v-else type="primary" :disabled="!input.trim() || !currentProfileId" @click="onSend">
							{{ t('agent.session.send') }}
						</el-button>
					</div>
				</div>
			</main>
		</div>
	</cl-crud>
</template>

<script lang="ts" setup name="agent-session">
import { onMounted, nextTick, ref, watch } from 'vue';
import { useCrud } from '@cool-vue/crud';
import { Loading } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';
import ChatMessage from '../components/chat-message.vue';
import { useAgentSession } from '../composables/use-agent-session';

const { service } = useCool();
const { t } = useI18n();

// cl-crud 骨架承载权限指令（页面本体为交互式会话，非标准表格）
const Crud = useCrud({ service: service.agent.session }, (app) => {
	app.service.refresh();
});

const {
	profiles,
	publishedProfiles,
	sessions,
	currentSessionId,
	currentProfileId,
	messages,
	running,
	runningTool,
	traceToken,
	stopHint,
	streamingText,
	loadProfiles,
	loadSessions,
	openSession,
	newSession,
	send,
	stop
} = useAgentSession({ mode: 'published' });

const input = ref('');
const messageListRef = ref<HTMLDivElement>();

async function refresh() {
	await Promise.all([loadProfiles(), loadSessions()]);
}

async function onSend() {
	const question = input.value.trim();
	if (!question || running.value) return;
	input.value = '';
	await send(question);
}

function formatTime(value?: string) {
	if (!value) return '';
	return String(value).replace('T', ' ').slice(5, 16);
}

watch(currentProfileId, () => {
	newSession();
});

watch(
	() => messages.value.length + streamingText.value.length,
	() => {
		nextTick(() => {
			messageListRef.value?.scrollTo({ top: messageListRef.value.scrollHeight });
		});
	}
);

onMounted(refresh);
</script>

<style lang="scss" scoped>
.agent-session-page {
	display: flex;
	height: calc(100vh - 120px);
	background-color: var(--el-bg-color);
	border-radius: 6px;
	overflow: hidden;
}

.side-panel {
	width: 260px;
	border-right: 1px solid var(--el-border-color-lighter);
	display: flex;
	flex-direction: column;
	flex-shrink: 0;
}

.side-section {
	padding: 12px;
	border-bottom: 1px solid var(--el-border-color-lighter);

	&:last-child {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		border-bottom: none;
	}
}

.side-title {
	display: flex;
	justify-content: space-between;
	align-items: center;
	font-size: 13px;
	color: var(--el-text-color-secondary);
	margin-bottom: 8px;
}

.profile-select {
	width: 100%;
}

.session-list {
	flex: 1;
	overflow-y: auto;
}

.session-item {
	padding: 8px 10px;
	border-radius: 6px;
	cursor: pointer;
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 4px;

	&:hover {
		background-color: var(--el-fill-color-light);
	}

	&.active {
		background-color: var(--el-color-primary-light-9);

		.session-title {
			color: var(--el-color-primary);
		}
	}

	.session-title {
		font-size: 13px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.session-time {
		font-size: 12px;
		color: var(--el-text-color-secondary);
		flex-shrink: 0;
	}
}

.session-empty {
	color: var(--el-text-color-secondary);
	font-size: 13px;
	text-align: center;
	padding: 16px 0;
}

.chat-panel {
	flex: 1;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.message-list {
	flex: 1;
	overflow-y: auto;
	padding: 16px;
}

.chat-placeholder {
	color: var(--el-text-color-secondary);
	text-align: center;
	margin-top: 20%;
}

.live-tool {
	display: flex;
	align-items: center;
	gap: 6px;
	color: var(--el-color-primary);
	font-size: 13px;
	margin: 8px 0;
}

.bubble.streaming {
	background-color: var(--el-fill-color-light);
	padding: 8px 12px;
	border-radius: 8px;
	max-width: 76%;
	white-space: pre-wrap;
	margin: 8px 0;
}

.stop-hint {
	margin: 8px 0;
}

.input-area {
	border-top: 1px solid var(--el-border-color-lighter);
	padding: 12px;
}

.input-actions {
	display: flex;
	justify-content: flex-end;
	align-items: center;
	gap: 8px;
	margin-top: 8px;

	.hint {
		color: var(--el-text-color-secondary);
		font-size: 12px;
		margin-right: auto;
	}
}
</style>
