<template>
	<el-drawer v-model="visible" :title="t('agent.trace.detail')" size="62%" destroy-on-close>
		<div v-loading="loadingInfo" class="trace-detail">
			<el-descriptions :column="2" size="small" border>
				<el-descriptions-item :label="t('agent.trace.agent')">{{ detail.agentName }}</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.mode')">
					<el-tag size="small" effect="plain" :type="detail.runMode === 'published' ? 'success' : 'warning'">
						{{ modeText(detail.runMode) }}
					</el-tag>
				</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.status')">
					<!-- 与列表同源语义色（dictColor 按索引染主题色板，不能复用） -->
					<el-tag size="small" effect="dark" :color="statusColor(detail.status)">
						{{ statusText(detail.status) }}
					</el-tag>
				</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.duration')">
					{{ humanizeDuration(detail.durationMs) }}
				</el-descriptions-item>
				<el-descriptions-item :label="t('agent.profile.createTime')">
					{{ formatDateTime(detail.createTime) }}
				</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.tokensDetail')">
					{{ formatTokens(detail.promptTokens, detail.completionTokens) }}
				</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.modelCalls')">{{ detail.modelCalls ?? 0 }}</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.toolRounds')">{{ detail.toolRounds ?? 0 }}</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.toolCalls')">{{ detail.toolCalls ?? 0 }}</el-descriptions-item>
				<!-- D16：本次 run 实际使用的护栏版本（编排型无护栏显示 -） -->
				<el-descriptions-item :label="t('agent.trace.guardrails')">
					{{ detail.guardrailsVersion ?? '-' }}
				</el-descriptions-item>
				<el-descriptions-item :label="t('agent.trace.ids')" :span="2">
					<span class="mono">#{{ detail.id }}</span>
					<el-divider direction="vertical" />
					<span class="mono">{{ t('agent.trace.sessionShort') }} #{{ detail.sessionId }}</span>
					<el-link
						v-if="detail.sessionId"
						type="primary"
						:underline="false"
						class="jump-link"
						@click="goSession"
					>
						{{ t('agent.trace.jumpSession') }}
					</el-link>
				</el-descriptions-item>
				<!-- E17：编排型 run 回链工作流实例 -->
				<el-descriptions-item v-if="detail.workflowInstanceId" :label="t('agent.trace.workflowInstance')" :span="2">
					<el-link type="primary" :underline="false" @click="goWorkflow">
						{{ t('agent.trace.jumpWorkflow', { n: detail.workflowInstanceId }) }}
					</el-link>
				</el-descriptions-item>
			</el-descriptions>
			<el-alert v-if="detail.error" :title="detail.error" type="warning" :closable="false" class="trace-error" />

			<div class="section-title">{{ t('agent.trace.toolLogs') }}</div>
			<tool-trace-panel :logs="toolBlocks" />

			<div class="section-title">{{ t('agent.trace.messages') }}</div>
			<trace-messages :messages="detailMessages" :trace="detail" :inaccessible="messagesInaccessible" />
		</div>
	</el-drawer>
</template>

<script lang="ts" setup name="agent-trace-detail-drawer">
import { onUnmounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';
import ToolTracePanel, { type TraceBlock } from './tool-trace-panel.vue';
import TraceMessages from './trace-messages.vue';
import {
	TRACE_TERMINAL_STATUSES,
	formatDateTime,
	formatTokens,
	humanizeDuration,
	traceStatusItem
} from '../utils/trace-format';

const { service, router } = useCool();
const { t } = useI18n();

const visible = ref(false);
const loadingInfo = ref(false);
const detail = ref<any>({});
const toolBlocks = ref<TraceBlock[]>([]);
const detailMessages = ref<any[]>([]);
const messagesInaccessible = ref(false);

/** 非终态轮询（running/waiting_approval 行自动刷新，终态/关闭即停） */
let pollTimer: ReturnType<typeof setInterval> | null = null;
const POLL_INTERVAL_MS = 10_000;

function open(row: any) {
	visible.value = true;
	detail.value = { ...row };
	toolBlocks.value = [];
	detailMessages.value = [];
	messagesInaccessible.value = false;
	loadAll();
}

async function loadAll() {
	await Promise.all([refreshInfo(), refreshToolLogs(), refreshMessages()]);
	schedulePolling();
}

/** info 重取（列表行数据兜底——running 行在列表快照后可能已到终态） */
async function refreshInfo() {
	if (!detail.value.id) return;
	loadingInfo.value = true;
	try {
		detail.value = await service.agent.trace.info({ id: detail.value.id });
	} catch {
		// 保留列表行数据兜底
	} finally {
		loadingInfo.value = false;
	}
}

async function refreshToolLogs() {
	try {
		const logs = await service.agent.trace.toolLogs({ trace_id: detail.value.id });
		toolBlocks.value = ((logs || []) as any[]).map((log: any) => ({
			toolCallId: String(log.id),
			toolName: log.toolName,
			// skipped（cancelled 等 success=NULL 但有原因）与 failed（success=false）分开展示
			status: log.success === false ? ('failed' as const) : log.skippedReason ? ('skipped' as const) : ('done' as const),
			duration: log.durationMs ?? undefined,
			timestamp: log.createTime ?? undefined,
			targetRef: log.targetRef ?? undefined,
			skippedReason: log.skippedReason ?? undefined,
			argsSummary: log.argsSummary ?? undefined,
			resultSummary: log.resultSummary ?? undefined,
			error: log.error ?? undefined
		}));
	} catch {
		toolBlocks.value = []; // 越权/无明细时留空（消息轨迹仍在）
	}
}

async function refreshMessages() {
	try {
		const messages = await service.agent.session.messages({ session_id: detail.value.sessionId });
		detailMessages.value = (messages || []) as any[];
		messagesInaccessible.value = false;
	} catch {
		detailMessages.value = []; // 他人会话（管理员查看 trace）消息不可见——显式提示而非静默空白
		messagesInaccessible.value = true;
	}
}

function schedulePolling() {
	stopPolling();
	if (TRACE_TERMINAL_STATUSES.has(detail.value?.status)) return;
	pollTimer = setInterval(async () => {
		await Promise.all([refreshInfo(), refreshToolLogs()]);
		if (TRACE_TERMINAL_STATUSES.has(detail.value?.status)) stopPolling();
	}, POLL_INTERVAL_MS);
}

function stopPolling() {
	if (pollTimer) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
}

watch(visible, (v) => {
	if (!v) stopPolling();
});
onUnmounted(stopPolling);

function statusText(status?: string) {
	return status ? t(traceStatusItem(status)?.label || 'agent.trace.status') : '-';
}

function statusColor(status?: string) {
	return traceStatusItem(status)?.color;
}

function modeText(mode?: string) {
	if (mode === 'draft') return t('agent.trace.modeDraft');
	if (mode === 'published') return t('agent.trace.modePublished');
	return mode || '-';
}

function goSession() {
	router.push({ path: '/agent/session', query: { sessionId: detail.value.sessionId } });
}

function goWorkflow() {
	router.push({ path: '/workflow/instance', query: { instanceId: detail.value.workflowInstanceId } });
}

defineExpose({ open });
</script>

<style lang="scss" scoped>
.trace-detail {
	padding: 12px;

	.mono {
		font-family: var(--el-font-family, monospace);
		font-size: 12px;
		color: var(--el-text-color-regular);
	}

	.jump-link {
		margin-left: 8px;
		font-size: 12px;
		vertical-align: middle;
	}

	.trace-error {
		margin-top: 8px;
	}

	.section-title {
		font-size: 13px;
		color: var(--el-text-color-secondary);
		margin: 16px 0 8px;
	}
}
</style>
