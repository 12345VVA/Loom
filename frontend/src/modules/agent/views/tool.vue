<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-filter :label="t('agent.tool.level')">
				<cl-select :options="levelOptions" prop="level" :width="150" clearable />
			</cl-filter>
			<cl-flex1 />
			<!-- degraded 徽标（D14 可见性）：registryStatus 页面级一次性加载，不进 useCrud 刷新链；
			     refresh 仅 DB 同步、不清 degraded（文案不承诺"修复降级"） -->
			<el-tag v-if="registry.degraded" type="danger" effect="dark">
				{{ t('agent.tool.degradedBadge') }}
			</el-tag>
			<el-tag v-else type="success" effect="plain">
				{{ t('agent.tool.registryOk') }} · {{ registry.toolCount }}
			</el-tag>
			<el-button v-permission="serviceTool.permission?.refresh" :loading="refreshing" @click="onRefresh">
				{{ t('agent.tool.refresh') }}
			</el-button>
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #column-status="{ scope }">
					<el-switch
						v-permission="serviceTool.permission?.toggleEnabled"
						:model-value="scope.row.status"
						@change="val => onToggle(scope.row, Boolean(val))"
					/>
				</template>
				<template #slot-op="{ scope }">
					<el-button
						v-permission="serviceTool.permission?.versions"
						text
						type="primary"
						@click="openVersions(scope.row)"
					>
						{{ t('agent.tool.versions') }}
					</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<!-- E12 版本历史：version 倒序；契约哈希截前 8 位（完整值看详情） -->
		<el-drawer v-model="versionsVisible" :title="versionsTitle" size="50%" destroy-on-close>
			<el-table :data="versions" size="small">
				<el-table-column prop="version" label="#" width="70" />
				<el-table-column prop="changeKind" :label="t('agent.tool.changeKind')" width="150" />
				<el-table-column prop="level" :label="t('agent.tool.level')" width="150" />
				<el-table-column :label="t('agent.tool.contractHash')" width="110">
					<template #default="{ row }">{{ (row.contractHash || '').slice(0, 8) }}</template>
				</el-table-column>
				<el-table-column prop="createTime" :label="t('agent.profile.createTime')" width="165" />
			</el-table>
		</el-drawer>
	</cl-crud>
</template>

<script lang="ts" setup name="agent-tool">
import { onMounted, ref } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';

const { service } = useCool();
const { t } = useI18n();
const serviceTool = service.agent.tool;

// 行形态（对齐 eps.d.ts interface tool / version：resolve_alias camelCase 出口）
type ToolRow = {
	id: number;
	toolName: string;
	displayName?: string;
	level?: string;
	status?: boolean;
	sourceType?: string;
	createTime?: string;
};
type ToolVersionRow = {
	version: number;
	changeKind?: string;
	level?: string;
	contractHash?: string;
	createTime?: string;
};

// 工具等级（三级枚举，D11 语义）：dangerous_write 当前不可发布（D11 前置），仅展示
const levelOptions = [
	{ label: t('agent.tool.levelReadonly'), value: 'readonly', type: 'info' },
	{ label: t('agent.tool.levelReversibleWrite'), value: 'reversible_write', type: 'warning' },
	{ label: t('agent.tool.levelDangerousWrite'), value: 'dangerous_write', type: 'danger' }
];

// 注册表状态（degraded 可见性）：启动收集失败时置位；sync 失败只 warning 不置位
const registry = ref<{ degraded: boolean; error?: string; toolCount: number }>({
	degraded: false,
	toolCount: 0
});
const refreshing = ref(false);

onMounted(async () => {
	try {
		const status = await serviceTool.registryStatus();
		registry.value = (status || {}) as { degraded: boolean; error?: string; toolCount: number };
	} catch {
		registry.value = { degraded: false, toolCount: 0 };
	}
});

// 标准 CRUD 实例（crud.mdc：标准启动刷新统一为 app.refresh()）
const Crud = useCrud(
	{
		service: serviceTool
	},
	(app) => {
		app.refresh();
	}
);

// 表格配置；status 为 boolean 开关列（受控 model-value，成功后才更新行值）
const Table = useTable({
	columns: [
		{ type: 'index', label: '#', width: 50 },
		{ prop: 'toolName', label: t('agent.tool.toolName'), minWidth: 170 },
		{ prop: 'displayName', label: t('agent.tool.displayName'), minWidth: 140 },
		{
			prop: 'level',
			label: t('agent.tool.level'),
			width: 140,
			flex: false,
			dict: levelOptions,
			dictColor: true
		},
		{
			prop: 'status',
			label: t('agent.tool.enabled'),
			width: 90,
			flex: false
		},
		{ prop: 'sourceType', label: t('agent.tool.sourceType'), width: 100, flex: false },
		{ prop: 'createTime', label: t('agent.profile.createTime'), width: 165, flex: false },
		{
			type: 'op',
			width: 100,
			fixed: 'right',
			buttons: ['slot-op']
		}
	],
	contextMenu: ['refresh']
});

// D14 紧急启停：实时生效（执行链 assert_execution_allowed 实时查库）；
// 停用影响所有运行中智能体，二次确认；失败不更新行值
async function onToggle(row: ToolRow, val: boolean) {
	if (!val) {
		try {
			await ElMessageBox.confirm(
				t('agent.tool.toggleOffConfirm', { name: row.displayName || row.toolName }),
				t('agent.tool.toggleOffTitle'),
				{ type: 'warning' }
			);
		} catch {
			return;
		}
	}
	try {
		const updated = (await serviceTool.toggleEnabled({ id: row.id, status: val })) as ToolRow | undefined;
		row.status = updated?.status ?? val;
		ElMessage.success(t(val ? 'agent.tool.toggleOn' : 'agent.tool.toggleOff'));
	} catch (e) {
		ElMessage.error(t('agent.tool.toggleFailed') + (e instanceof Error ? e.message : String(e)));
	}
}

// 资源层同步（不重建执行注册表）：恢复被代码更新覆盖的展示/契约字段
async function onRefresh() {
	refreshing.value = true;
	try {
		const res = (await serviceTool.refresh()) as { ok?: boolean; count?: number } | undefined;
		ElMessage.success(t('agent.tool.refreshSuccess', { count: res?.count ?? 0 }));
		Crud.value?.refresh();
	} catch (e) {
		ElMessage.error(t('agent.tool.refreshFailed') + (e instanceof Error ? e.message : String(e)));
	} finally {
		refreshing.value = false;
	}
}

const versionsVisible = ref(false);
const versionsTitle = ref('');
const versions = ref<ToolVersionRow[]>([]);

async function openVersions(row: ToolRow) {
	versionsTitle.value = `${row.displayName || row.toolName} · ${t('agent.tool.versions')}`;
	try {
		const list = await serviceTool.versions({ toolName: row.toolName });
		versions.value = (list || []) as ToolVersionRow[];
	} catch {
		versions.value = [];
	}
	versionsVisible.value = true;
}
</script>
