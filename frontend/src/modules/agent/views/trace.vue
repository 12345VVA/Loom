<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-filter :label="t('agent.trace.status')">
				<cl-select :options="statusOptions" prop="status" :width="130" clearable />
			</cl-filter>
			<cl-flex1 />
			<cl-search-key :placeholder="t('agent.trace.searchPlaceholder')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<el-button
						v-permission="serviceTrace.permission?.info"
						text
						type="primary"
						@click="openDetail(scope.row)"
					>
						{{ t('agent.trace.detailBtn') }}
					</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<!-- 详情 drawer：消息轨迹 + 工具明细 -->
		<el-drawer v-model="detailVisible" :title="t('agent.trace.detail')" size="60%" destroy-on-close>
			<div class="trace-detail">
				<el-descriptions :column="2" size="small" border>
					<el-descriptions-item :label="t('agent.trace.agent')">{{ detail.agentName }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.mode')">{{ detail.runMode }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.status')">{{ detail.status }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.duration')">{{ detail.durationMs }}ms</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.modelCalls')">{{ detail.modelCalls }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.toolRounds')">{{ detail.toolRounds }}</el-descriptions-item>
					<!-- D16：本次 run 实际使用的护栏版本（编排型无护栏显示 -） -->
					<el-descriptions-item :label="t('agent.trace.guardrails')">
						{{ detail.guardrailsVersion ?? '-' }}
					</el-descriptions-item>
				</el-descriptions>
				<el-alert
					v-if="detail.error"
					:title="detail.error"
					type="warning"
					:closable="false"
					class="trace-error"
				/>

				<div class="section-title">{{ t('agent.trace.toolLogs') }}</div>
				<tool-trace-panel :logs="toolBlocks" />

				<div class="section-title">{{ t('agent.trace.messages') }}</div>
				<chat-message v-for="(m, i) in detailMessages" :key="i" :message="m" />
			</div>
		</el-drawer>
	</cl-crud>
</template>

<script lang="ts" setup name="agent-trace">
import { ref } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';
import ChatMessage from '../components/chat-message.vue';
import ToolTracePanel, { type TraceBlock } from '../components/tool-trace-panel.vue';

const { service } = useCool();
const { t } = useI18n();
const serviceTrace = service.agent.trace;

// 状态字典（cool-crud-conventions.mdc：简单枚举复用 dict 与 dictColor）；waiting_approval 为 E4 非终态
const statusOptions = [
	{ label: t('agent.trace.statusRunning'), value: 'running', type: 'primary' },
	{ label: t('agent.trace.statusWaitingApproval'), value: 'waiting_approval', type: 'warning' },
	{ label: t('agent.trace.statusCompleted'), value: 'completed', type: 'success' },
	{ label: t('agent.trace.statusFailed'), value: 'failed', type: 'danger' },
	{ label: t('agent.trace.statusCancelled'), value: 'cancelled', type: 'info' },
	{ label: t('agent.trace.statusTimedOut'), value: 'timed_out', type: 'warning' }
];

const detailVisible = ref(false);
const detail = ref<any>({});
const toolBlocks = ref<TraceBlock[]>([]);
const detailMessages = ref<any[]>([]);

// 标准 CRUD 实例（crud.mdc：标准启动刷新统一为 app.refresh()）
const Crud = useCrud(
	{
		service: serviceTrace
	},
	(app) => {
		app.refresh();
	}
);

// 表格配置
const Table = useTable({
	columns: [
		{ type: 'index', label: '#', width: 50 },
		{ prop: 'agentName', label: t('agent.trace.agent'), minWidth: 130 },
		{
			prop: 'runMode',
			label: t('agent.trace.mode'),
			width: 90,
			flex: false
		},
		{
			prop: 'status',
			label: t('agent.trace.status'),
			width: 110,
			flex: false,
			dict: statusOptions,
			dictColor: true
		},
		{ prop: 'modelCalls', label: t('agent.trace.modelCalls'), width: 90, flex: false },
		{ prop: 'toolRounds', label: t('agent.trace.toolRounds'), width: 90, flex: false },
		{ prop: 'durationMs', label: t('agent.trace.duration'), width: 100, flex: false },
		{ prop: 'createTime', label: t('agent.profile.createTime'), width: 165, flex: false, component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 90,
			fixed: 'right',
			buttons: ['slot-op']
		}
	],
	contextMenu: ['refresh']
});

async function openDetail(row: any) {
	detail.value = row;
	toolBlocks.value = [];
	detailMessages.value = [];
	try {
		const messages = await service.agent.session.messages({ session_id: row.sessionId });
		detailMessages.value = (messages || []) as any[];
	} catch {
		detailMessages.value = []; // 他人会话（管理员查看 trace）消息不可见——仅展示计数面
	}
	// 工具明细走 tool_call_log（观测二级：参数摘要/结果摘要/耗时/成败——非消息拼凑）
	try {
		const logs = await service.agent.trace.toolLogs({ trace_id: row.id });
		toolBlocks.value = ((logs || []) as any[]).map((log: any) => ({
			toolCallId: String(log.id),
			toolName: log.toolName,
			// skipped（cancelled 等 success=NULL 但有原因）与 failed（success=false）分开展示
			status: log.success === false ? ('failed' as const) : log.skippedReason ? ('skipped' as const) : ('done' as const),
			duration: log.durationMs ?? undefined,
			skippedReason: log.skippedReason ?? undefined,
			argsSummary: log.argsSummary ?? undefined,
			resultSummary: log.resultSummary ?? undefined,
			error: log.error ?? undefined
		}));
	} catch {
		toolBlocks.value = []; // 越权/无明细时留空（消息轨迹仍在）
	}
	detailVisible.value = true;
}
</script>

<style lang="scss" scoped>
.trace-detail {
	padding: 12px;

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
