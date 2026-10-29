<template>
	<div class="trace-messages">
		<!-- 他人会话（管理员查 trace）消息不可见：显式提示，与「没有消息」区分 -->
		<el-alert
			v-if="inaccessible"
			:title="t('agent.trace.messagesInaccessible')"
			type="info"
			:closable="false"
		/>
		<template v-else>
			<div v-if="(messages?.length || 0) > 0" class="scope-bar">
				<el-radio-group v-model="scope" size="small">
					<el-radio-button value="run">{{ t('agent.trace.scopeRun', { n: runCount }) }}</el-radio-button>
					<el-radio-button value="full">{{ t('agent.trace.scopeFull', { n: messages.length }) }}</el-radio-button>
				</el-radio-group>
			</div>

			<div v-if="!visibleMessages.length" class="empty">{{ t('agent.trace.noRunMessages') }}</div>

			<template v-for="(m, i) in visibleMessages" :key="m.id ?? i">
				<!-- 工具决策轮：无文本回复的 assistant 气泡收敛为紧凑 chip（与工具结果块对称） -->
				<div v-if="isToolCallTurn(m)" class="tool-call-turn">
					<el-icon><set-up /></el-icon>
					<span class="turn-label">{{ t('agent.trace.toolCallTurn') }}</span>
					<el-tag v-for="(c, ci) in parseToolCallTurn(m)" :key="c.id ?? ci" size="small" effect="plain">
						{{ c.name || '?' }}
					</el-tag>
				</div>
				<chat-message v-else :message="m" />
			</template>
		</template>
	</div>
</template>

<script lang="ts" setup name="agent-trace-messages">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { SetUp } from '@element-plus/icons-vue';
import ChatMessage from './chat-message.vue';
import { type TraceMessageRow, type TraceRow, filterRunMessages, isToolCallTurn, parseToolCallTurn } from '../utils/trace-format';

const props = defineProps<{
	/** 会话全量消息（session.messages 无 run 维度） */
	messages: TraceMessageRow[];
	/** trace 行（createTime/durationMs 构成时间窗） */
	trace: TraceRow | null;
	/** 消息接口 403（非本人会话） */
	inaccessible?: boolean;
}>();

const { t } = useI18n();

const scope = ref<'run' | 'full'>('run');

const runMessages = computed(() => filterRunMessages(props.messages || [], props.trace));
const runCount = computed(() => runMessages.value.length);
const visibleMessages = computed(() => (scope.value === 'run' ? runMessages.value : props.messages || []));
</script>

<style lang="scss" scoped>
.trace-messages {
	.scope-bar {
		margin-bottom: 12px;
	}

	.empty {
		color: var(--el-text-color-secondary);
		font-size: 13px;
		text-align: center;
		padding: 16px 0;
	}

	.tool-call-turn {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 14px;
		padding: 6px 12px;
		border-radius: 8px;
		border: 1px dashed var(--el-border-color-lighter);
		background: var(--el-fill-color-lighter);
		width: fit-content;
		color: var(--el-text-color-secondary);
		font-size: 13px;

		.turn-label {
			font-weight: 500;
		}
	}
}
</style>
