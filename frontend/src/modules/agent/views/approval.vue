<template>
	<cl-crud ref="Crud">
		<!-- E4 冻结标注（D11 预置未解冻）：发布校验禁止 dangerous_write 与审批门槛互斥，
		     审批链当前永无触发可能；service/表/巡检任务实现保留，解冻随第一个 dangerous_write 工具立项 -->
		<el-alert
			:title="t('agent.approval.experimental')"
			type="info"
			show-icon
			:closable="false"
			style="margin-bottom: 8px"
		/>
		<cl-row>
			<cl-refresh-btn />
			<cl-filter :label="t('agent.approval.status')">
				<cl-select :options="statusOptions" prop="status" :width="130" clearable />
			</cl-filter>
			<cl-flex1 />
			<cl-search-key :placeholder="t('agent.approval.searchPlaceholder')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<template v-if="scope.row.status === 'pending'">
						<el-button
							v-permission="serviceApproval.permission?.decide"
							text
							type="success"
							@click="decide(scope.row, 'approve')"
						>
							{{ t('agent.approval.approve') }}
						</el-button>
						<el-button
							v-permission="serviceApproval.permission?.decide"
							text
							type="danger"
							@click="decide(scope.row, 'reject')"
						>
							{{ t('agent.approval.reject') }}
						</el-button>
					</template>
					<template v-else-if="scope.row.status === 'executing'">
						<!-- 租约残留人工核对（A25）：重试仅只读工具（后端强制）；或人工标记结果 -->
						<el-button
							v-permission="serviceApproval.permission?.reconcile"
							text
							type="warning"
							@click="retry(scope.row)"
						>
							{{ t('agent.approval.retry') }}
						</el-button>
						<el-button
							v-permission="serviceApproval.permission?.reconcile"
							text
							type="info"
							@click="reconcile(scope.row, 'failed')"
						>
							{{ t('agent.approval.markFailed') }}
						</el-button>
					</template>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>
</template>

<script lang="ts" setup name="agent-approval">
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';

const { service } = useCool();
const { t } = useI18n();
const serviceApproval = service.agent.approval;

// 审批八值状态机（二批 3.5）：pending → approved → executing → succeeded/failed；pending → rejected/expired/cancelled
const statusOptions = [
	{ label: t('agent.approval.statusPending'), value: 'pending', type: 'warning' },
	{ label: t('agent.approval.statusApproved'), value: 'approved', type: 'success' },
	{ label: t('agent.approval.statusExecuting'), value: 'executing', type: 'primary' },
	{ label: t('agent.approval.statusSucceeded'), value: 'succeeded', type: 'success' },
	{ label: t('agent.approval.statusFailed'), value: 'failed', type: 'danger' },
	{ label: t('agent.approval.statusRejected'), value: 'rejected', type: 'danger' },
	{ label: t('agent.approval.statusExpired'), value: 'expired', type: 'info' },
	{ label: t('agent.approval.statusCancelled'), value: 'cancelled', type: 'info' }
];

const Crud = useCrud(
	{
		service: serviceApproval
	},
	(app) => {
		app.refresh();
	}
);

const Table = useTable({
	columns: [
		{ type: 'index', label: '#', width: 50 },
		{ prop: 'toolName', label: t('agent.approval.toolName'), minWidth: 140 },
		{
			prop: 'argsSummary',
			label: t('agent.approval.args'),
			minWidth: 180,
			showOverflowTooltip: true
		},
		{
			prop: 'status',
			label: t('agent.approval.status'),
			width: 100,
			flex: false,
			dict: statusOptions,
			dictColor: true
		},
		{ prop: 'requestedBy', label: t('agent.approval.requestedBy'), width: 90, flex: false },
		{ prop: 'approver', label: t('agent.approval.approver'), width: 90, flex: false },
		{ prop: 'expiresAt', label: t('agent.approval.expiresAt'), width: 165, flex: false },
		{ prop: 'resultSummary', label: t('agent.approval.result'), minWidth: 160, showOverflowTooltip: true },
		{ prop: 'createTime', label: t('agent.profile.createTime'), width: 165, flex: false, component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 170,
			fixed: 'right',
			buttons: ['slot-op']
		}
	],
	contextMenu: ['refresh']
});

/** 审批行最小类型（EPS 行模型失真收敛——asset 期坑⑩） */
interface ApprovalRow {
	id: number;
	toolName: string;
	status: string;
}

/** decide/reconcile 响应的最小类型（decide/reconcile/retry: {ok,status,resume:{resumed}}） */
interface DecideResult {
	ok?: boolean;
	resume?: { resumed?: boolean };
}

async function decide(row: ApprovalRow, action: 'approve' | 'reject') {
	const tip =
		action === 'approve'
			? t('agent.approval.approveTip', { name: row.toolName })
			: t('agent.approval.rejectTip', { name: row.toolName });
	await ElMessageBox.confirm(tip, t('agent.approval.decideTitle'), { type: action === 'approve' ? 'success' : 'warning' });
	const res = (await serviceApproval.decide({ id: row.id, action })) as unknown as DecideResult;
	ElMessage.success(res?.resume?.resumed ? t('agent.approval.resumed') : t('agent.approval.decided'));
	Crud.value?.refresh();
}

async function reconcile(row: ApprovalRow, outcome: 'succeeded' | 'failed') {
	await ElMessageBox.confirm(t('agent.approval.reconcileTip', { name: row.toolName }), t('agent.approval.reconcileTitle'), {
		type: 'warning'
	});
	await serviceApproval.reconcile({ id: row.id, outcome, note: '' });
	ElMessage.success(t('agent.approval.reconciled'));
	Crud.value?.refresh();
}

async function retry(row: ApprovalRow) {
	await ElMessageBox.confirm(t('agent.approval.retryTip', { name: row.toolName }), t('agent.approval.retryTitle'), {
		type: 'warning'
	});
	const res = (await serviceApproval.retry({ id: row.id, outcome: 'succeeded', note: '' })) as unknown as DecideResult;
	ElMessage.success(res?.ok ? t('agent.approval.retryOk') : t('agent.approval.retryFail'));
	Crud.value?.refresh();
}
</script>
