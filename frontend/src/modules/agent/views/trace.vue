<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-search-key />
			<cl-filter :label="t('agent.trace.status')" prop="status">
				<el-select v-model="statusFilter" clearable :placeholder="t('agent.trace.all')" @change="onFilter">
					<el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
				</el-select>
			</cl-filter>
			<cl-flex1 />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<!-- 详情 drawer：消息轨迹 + 工具明细 -->
		<cl-drawer v-model="detailVisible" :title="t('agent.trace.detail')" size="60%">
			<div class="trace-detail">
				<el-descriptions :column="2" size="small" border>
					<el-descriptions-item :label="t('agent.trace.agent')">{{ detail.agentName }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.mode')">{{ detail.runMode }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.status')">{{ detail.status }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.duration')">{{ detail.durationMs }}ms</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.modelCalls')">{{ detail.modelCalls }}</el-descriptions-item>
					<el-descriptions-item :label="t('agent.trace.toolRounds')">{{ detail.toolRounds }}</el-descriptions-item>
				</el-descriptions>
				<el-alert
					v-if="detail.error"
					:title="detail.error"
					type="warning"
					:closable="false"
					class="trace-error"
				/>

				<div class="section-title">{{ t('agent.trace.toolLogs') }}</div>
				<ToolTracePanel :logs="toolBlocks" />

				<div class="section-title">{{ t('agent.trace.messages') }}</div>
				<ChatMessage v-for="(m, i) in detailMessages" :key="i" :message="m" />
			</div>
		</cl-drawer>
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

const statuses = ['completed', 'failed', 'cancelled', 'timed_out'];
const statusFilter = ref<string>('');

const detailVisible = ref(false);
const detail = ref<any>({});
const toolBlocks = ref<TraceBlock[]>([]);
const detailMessages = ref<any[]>([]);

function onFilter() {
	Crud.value?.refresh();
}

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
			tag: true
		},
		{ prop: 'modelCalls', label: t('agent.trace.modelCalls'), width: 90, flex: false },
		{ prop: 'toolRounds', label: t('agent.trace.toolRounds'), width: 90, flex: false },
		{ prop: 'durationMs', label: t('agent.trace.duration'), width: 100, flex: false },
		{ prop: 'createTime', label: t('agent.profile.createTime'), width: 165, flex: false },
		{
			type: 'op',
			width: 80,
			buttons: [
				({ row }: any) => ({
					label: t('agent.trace.detailBtn'),
					onClick: () => openDetail(row)
				})
			]
		}
	]
});

async function openDetail(row: any) {
	detail.value = row;
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
			status: log.success === false ? ('failed' as const) : ('done' as const),
			duration: log.durationMs ?? undefined
		}));
	} catch {
		toolBlocks.value = []; // 越权/无明细时留空（消息轨迹仍在）
	}
	detailVisible.value = true;
}

const Crud = useCrud(
	{
		service: serviceTrace,
		onRefresh(params: any, { next }: any) {
			next({ ...params, status: statusFilter.value || undefined });
		}
	},
	(app) => {
		app.service.refresh();
	}
);
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
