<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-filter :label="t('agent.trace.status')">
				<cl-select :options="statusOptions" prop="status" :width="130" clearable />
			</cl-filter>
			<cl-filter :label="t('agent.trace.mode')">
				<cl-select :options="modeOptions" prop="runMode" :width="110" clearable />
			</cl-filter>
			<cl-filter :label="t('agent.profile.createTime')">
				<!-- prop 对接后端 apply_ranges：created_atStartTime / created_atEndTime -->
				<cl-date-picker prop="created_at" style="width: 240px" />
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

		<!-- 详情抽屉（组件化：数据编排/轮询/跳转在 trace-detail-drawer） -->
		<trace-detail-drawer ref="DetailDrawer" />
	</cl-crud>
</template>

<script lang="ts" setup name="agent-trace">
import { ref } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';
import TraceDetailDrawer from '../components/trace-detail-drawer.vue';
import {
	TRACE_MODE_OPTIONS,
	TRACE_STATUS_OPTIONS,
	type TraceRow,
	formatTokens,
	humanizeDuration
} from '../utils/trace-format';

const { service } = useCool();
const { t } = useI18n();
const serviceTrace = service.agent.trace;

// 状态字典：显式语义色（dictColor 按数组索引染主题色板，与 type 语义无关——
// 不给 color 会出现「已完成=紫、失败=浅蓝」的错位）；waiting_approval 为 E4 非终态
const statusOptions = TRACE_STATUS_OPTIONS.map((s) => ({ label: t(s.label), value: s.value, color: s.color }));
const modeOptions = TRACE_MODE_OPTIONS.map((m) => ({ label: t(m.label), value: m.value }));

const DetailDrawer = ref<InstanceType<typeof TraceDetailDrawer>>();

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
			flex: false,
			dict: modeOptions
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
		{
			prop: 'promptTokens',
			label: t('agent.trace.tokens'),
			width: 120,
			flex: false,
			formatter: (row: TraceRow) => formatTokens(row.promptTokens, row.completionTokens)
		},
		{
			prop: 'durationMs',
			label: t('agent.trace.duration'),
			width: 100,
			flex: false,
			sortable: 'custom',
			formatter: (row: TraceRow) => humanizeDuration(row.durationMs)
		},
		{ prop: 'createTime', label: t('agent.profile.createTime'), width: 165, flex: false, sortable: 'desc', component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 90,
			fixed: 'right',
			buttons: ['slot-op']
		}
	],
	contextMenu: ['refresh']
});

function openDetail(row: TraceRow) {
	DetailDrawer.value?.open(row);
}
</script>
