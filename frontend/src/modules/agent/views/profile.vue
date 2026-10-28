<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn :label="t('agent.profile.add')" />
			<cl-filter :label="t('agent.profile.status')">
				<cl-select :options="statusOptions" prop="status" :width="120" clearable />
			</cl-filter>
			<cl-flex1 />
			<!-- 批量删除降权：智能体低频删除，后移出主操作梯队（靠右与搜索区同侧） -->
			<cl-multi-delete-btn />
			<cl-search-key :placeholder="t('agent.profile.searchPlaceholder')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<!-- 状态 + 脏标记（发布与版本分析 P1-1：编辑已发布智能体后未再发布时可见） -->
				<template #column-status="{ scope }">
					<el-tag
						:type="scope.row.status === 'published' ? 'success' : 'info'"
						effect="light"
						class="status-tag"
					>
						{{ statusOptions.find((o) => o.value === scope.row.status)?.label || scope.row.status }}
					</el-tag>
					<el-tag v-if="scope.row.hasPendingChanges" type="warning" effect="light" class="status-tag">
						{{ t('agent.profile.pendingChanges') }}
					</el-tag>
				</template>
				<!-- 名称 + 描述合并（描述灰色副文本，省一列） -->
				<template #column-name="{ scope }">
					<div class="name-cell">
						<div class="cell-main">{{ scope.row.name }}</div>
						<div v-if="scope.row.description" class="cell-sub">{{ scope.row.description }}</div>
					</div>
				</template>
				<!-- 渠道显示名（code 灰色副文本） -->
				<template #column-modelProfileCode="{ scope }">
					<div class="name-cell">
						<div class="cell-main">{{ channelLabelOf(scope.row.modelProfileCode) }}</div>
						<div v-if="scope.row.modelProfileCode" class="cell-sub">{{ scope.row.modelProfileCode }}</div>
					</div>
				</template>
				<!-- 工具白名单：数量徽标 + 悬停明细（全量铺开曾把行高撑爆） -->
				<template #column-tools="{ scope }">
					<el-popover v-if="(scope.row.tools || []).length" placement="top" trigger="hover" width="300">
						<template #reference>
							<el-tag type="info" effect="plain" class="tools-badge">
								{{ t('agent.profile.toolsCount', { n: scope.row.tools.length }) }}
							</el-tag>
						</template>
						<div class="tools-list">
							<div v-for="tool in scope.row.tools" :key="tool" class="tools-item">
								{{ tool }}
							</div>
						</div>
					</el-popover>
					<span v-else>-</span>
				</template>
				<template #slot-op="{ scope }">
					<el-button
						v-permission="serviceAgent.permission?.debugChat"
						text
						type="primary"
						@click="openDebug(scope.row)"
					>
						{{ t('agent.profile.debug') }}
					</el-button>
					<el-button
						v-if="scope.row.status === 'draft' || scope.row.hasPendingChanges"
						v-permission="serviceAgent.permission?.publish"
						text
						type="success"
						@click="onPublish(scope.row)"
					>
						{{ t('agent.profile.publish') }}
					</el-button>
					<el-button
						v-permission="serviceAgent.permission?.update"
						text
						:type="scope.row.enabled ? 'danger' : 'primary'"
						@click="onToggle(scope.row)"
					>
						{{ scope.row.enabled ? t('agent.profile.disable') : t('agent.profile.enable') }}
					</el-button>
					<!-- 低频操作收敛进「更多」（版本/编辑/删除），操作列不再换行 -->
					<el-dropdown
						v-permission="{
							or: [
								serviceAgent.permission?.rollback,
								serviceAgent.permission?.update,
								serviceAgent.permission?.delete
							]
						}"
						trigger="click"
						@command="(cmd: string) => onMore(cmd, scope.row)"
					>
						<el-button text type="info">
							{{ t('agent.profile.more') }}
							<el-icon class="el-icon--right"><arrow-down /></el-icon>
						</el-button>
						<template #dropdown>
							<el-dropdown-menu>
								<el-dropdown-item
									v-if="scope.row.status === 'published'"
									v-permission="serviceAgent.permission?.rollback"
									command="versions"
								>
									{{ t('agent.profile.versions') }}
								</el-dropdown-item>
								<el-dropdown-item v-permission="serviceAgent.permission?.update" command="edit">
									{{ t('agent.profile.edit') }}
								</el-dropdown-item>
								<el-dropdown-item v-permission="serviceAgent.permission?.delete" command="delete">
									{{ t('agent.profile.delete') }}
								</el-dropdown-item>
							</el-dropdown-menu>
						</template>
					</el-dropdown>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert">
			<!-- 走查反馈：编号编辑态只读（新增可留空自动生成）；列表编号列已隐藏 -->
			<template #slot-code="{ scope }">
				<el-input
					:model-value="scope.code"
					:disabled="Upsert?.mode === 'update'"
					:placeholder="t('agent.profile.codePlaceholder')"
				/>
			</template>
		</cl-upsert>

		<!-- 调试台 drawer（draft 试聊，复用会话工作台 embedded 模式） -->
		<el-drawer v-model="debugVisible" :title="t('agent.debug.title')" size="55%" destroy-on-close>
			<chat-workspace
				v-if="debugVisible"
				mode="embedded"
				closable
				:draft-profile-id="debugProfileId"
				class="debug-workspace"
				@close="debugVisible = false"
			/>
		</el-drawer>

		<!-- 版本列表 drawer -->
		<el-drawer v-model="versionVisible" :title="t('agent.version.title')" size="45%" destroy-on-close>
			<el-table :data="versions" size="small">
				<el-table-column prop="version" :label="t('agent.version.no')" width="150">
					<template #default="{ row }">
						<span>v{{ row.version }}</span>
						<el-tag v-if="row.isCurrent" type="success" size="small" effect="light" class="status-tag">
							{{ t('agent.version.current') }}
						</el-tag>
					</template>
				</el-table-column>
				<el-table-column prop="createTime" :label="t('agent.version.time')" width="170">
					<template #default="{ row }">
						<cl-date-text :model-value="row.createTime" />
					</template>
				</el-table-column>
				<el-table-column prop="snapshotHash" :label="t('agent.version.hash')">
					<template #default="{ row }">
						<span class="hash-text">{{ (row.snapshotHash || '').slice(0, 12) }}</span>
					</template>
				</el-table-column>
				<el-table-column :label="t('agent.version.ops')" width="90">
					<template #default="{ row }">
						<el-button
							v-permission="serviceAgent.permission?.rollback"
							link
							type="primary"
							:disabled="row.isCurrent"
							size="small"
							@click="onRollback(row)"
						>
							{{ t('agent.profile.rollback') }}
						</el-button>
					</template>
				</el-table-column>
			</el-table>
		</el-drawer>
	</cl-crud>
</template>

<script lang="ts" setup name="agent-profile">
import { h, onMounted, ref } from 'vue';
import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useI18n } from 'vue-i18n';
import { ElIcon, ElMessage, ElMessageBox, ElTooltip } from 'element-plus';
import { InfoFilled, ArrowDown } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import ChatWorkspace from '../components/chat-workspace.vue';

const { service } = useCool();
const { t } = useI18n();
const serviceAgent = service.agent.profile;

// 状态字典选项（cool-crud-conventions.mdc：简单枚举使用 dict 与 dictColor）
const statusOptions = [
	{ label: t('agent.profile.statusDraft'), value: 'draft', type: 'info' },
	{ label: t('agent.profile.statusPublished'), value: 'published', type: 'success' }
];

const enabledOptions = [
	{ label: t('agent.profile.enabledOn'), value: true, type: 'success' },
	{ label: t('agent.profile.enabledOff'), value: false, type: 'danger' }
];

// 表单选项（挂载时预载）
const channelOptions = ref<any[]>([]);
const toolOptions = ref<any[]>([]);
const workflowOptions = ref<any[]>([]);

onMounted(async () => {
	try {
		const channels = await service.ai.profile.list();
		channelOptions.value = (channels || []).map((p: any) => ({ label: p.name, value: p.code }));
	} catch {
		channelOptions.value = [];
	}
	try {
		const tools = await service.agent.tool.list();
		// 禁用态灰显（工具链路专题 P1-5：发现层体现状态，不让用户配完发布才被拒）；
		// 不过滤以保留历史 profile 已选项的显示，发布校验仍兜底
		toolOptions.value = (tools || []).map((tool: any) => ({
			label: `${tool.displayName || tool.toolName}（${tool.level}）${tool.status ? '' : `（${t('agent.tool.disabled')}）`}`,
			value: tool.toolName,
			disabled: !tool.status
		}));
	} catch {
		toolOptions.value = [];
	}
	try {
		// 编排绑定候选 = 已启用且已发布的工作流定义（执行走现行发布版）
		type DefinitionRow = { id: number; name?: string; code?: string; isActive?: boolean; currentVersionId?: number };
		const defs = (await service.workflow.definition.list()) as unknown as DefinitionRow[];
		workflowOptions.value = (defs || [])
			.filter((d) => d.isActive && d.currentVersionId)
			.map((d) => ({ label: `${d.name || d.id}（${d.code || '-'}）`, value: d.id }));
	} catch {
		workflowOptions.value = [];
	}
});

// 调试台：draft 模式工作台
const debugVisible = ref(false);
const debugProfileId = ref<number | null>(null);

// 渠道显示名（渠道选项异步加载，未命中回落 code）
type ChannelOption = { label?: string; value?: string };
type ProfileRow = {
	id: number;
	name: string;
	status?: string;
	description?: string;
	modelProfileCode?: string;
	tools?: string[];
	hasPendingChanges?: boolean;
};

function channelLabelOf(code?: string) {
	if (!code) return '-';
	return channelOptions.value.find((c: ChannelOption) => c.value === code)?.label || code;
}

// 「更多」下拉：版本/编辑/删除（edit/delete 走 crud 实侧行方法，自带确认）
function onMore(cmd: string, row: ProfileRow) {
	if (cmd === 'versions') {
		openVersions(row);
	} else if (cmd === 'edit') {
		Crud.value?.rowEdit(row);
	} else if (cmd === 'delete') {
		Crud.value?.rowDelete(row);
	}
}

// 版本列表
const versionVisible = ref(false);
const versions = ref<any[]>([]);
const versionProfileId = ref<number | null>(null);

// ---- CRUD 实例 ----
const Crud = useCrud({ service: serviceAgent }, (app) => {
	app.refresh();
});

// ---- 表格（标准列布局 + permission 权限规范） ----
const Table = useTable({
	columns: [
		{ type: 'selection', width: 60 },
		{ type: 'index', label: '#', width: 50 },
		{ label: t('agent.profile.name'), prop: 'name', minWidth: 220 },
		{ label: t('agent.profile.modelProfile'), prop: 'modelProfileCode', width: 170, flex: false },
		{ label: t('agent.profile.tools'), prop: 'tools', width: 120, flex: false },
		{
			label: t('agent.profile.status'),
			prop: 'status',
			width: 100,
			dict: statusOptions,
			dictColor: true,
			flex: false
		},
		{
			label: t('agent.profile.enabled'),
			prop: 'enabled',
			width: 90,
			dict: enabledOptions,
			dictColor: true,
			flex: false
		},
		{ label: t('agent.profile.createTime'), prop: 'createTime', width: 160, flex: false, component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 230,
			fixed: 'right',
			buttons: ['slot-op']
		}
	],
	contextMenu: ['refresh', 'check', 'edit', 'delete']
});

// ---- Upsert（真实 prop 字段 + UI 规范图标化提示 + 数据初始化） ----
const Upsert = useUpsert({
	dialog: { width: '860px' },
	items: [
		{
			label: t('agent.profile.name'),
			prop: 'name',
			required: true,
			span: 12,
			// cool-vue 表单项无 component 时整个不渲染（isLoaded = e.component && ...）——
			// 名称输入框此前从未出现在新增/编辑弹窗（走查反馈「名称应该可以修改」的根源）
			component: { name: 'el-input', props: { maxlength: 150 } }
		},
		{
			label: t('agent.profile.code'),
			prop: 'code',
			span: 12,
			component: { name: 'slot-code' }
		},
		{
			label: t('agent.profile.modelProfile'),
			prop: 'modelProfileCode',
			required: true,
			span: 12,
			component: {
				name: 'el-select',
				options: channelOptions,
				props: { placeholder: t('agent.profile.modelProfilePlaceholder') }
			}
		},
		{
			label: t('agent.profile.description'),
			prop: 'description',
			span: 12,
			component: { name: 'el-input' }
		},
		{
			label: t('agent.profile.systemPrompt'),
			prop: 'systemPrompt',
			component: {
				name: 'el-input',
				props: { type: 'textarea', rows: 6, placeholder: t('agent.profile.systemPromptPlaceholder') }
			}
		},
		{
			label: t('agent.profile.tools'),
			prop: 'tools',
			component: {
				name: 'el-select',
				options: toolOptions,
				props: { multiple: true, placeholder: t('agent.profile.toolsPlaceholder') }
			}
		},
		{
			// E3 写工具知情确认：绑定 reversible_write 工具时发布校验强制（D11 二级治理）
			label: t('agent.profile.writeToolsAck'),
			prop: 'writeToolsAck',
			value: false,
			component: {
				name: 'el-switch',
				props: { activeText: t('agent.profile.writeToolsAckHint') }
			}
		},
		{
			label: t('agent.profile.temperature'),
			prop: 'temperature',
			span: 12,
			value: 0.5,
			component: { name: 'el-input-number', props: { min: 0, max: 2, step: 0.1 } }
		},
		{
			label: t('agent.profile.maxTokens'),
			prop: 'maxTokens',
			span: 12,
			value: 4000,
			component: { name: 'el-input-number', props: { min: 256, max: 26000, step: 256 } }
		},
		{
			label: t('agent.profile.maxToolRounds'),
			prop: 'maxToolRounds',
			span: 12,
			value: 12,
			component: { name: 'el-input-number', props: { min: 1, max: 50 } }
		},
		{
			label: t('agent.profile.timeoutSeconds'),
			prop: 'timeoutSeconds',
			span: 12,
			value: 60,
			component: { name: 'el-input-number', props: { min: 10, max: 600 } }
		},
		{
			label: t('agent.profile.enableMemory'),
			prop: 'enableMemory',
			span: 12,
			value: true,
			flex: false,
			component: { name: 'el-switch' }
		},
		{
			label: t('agent.profile.executionMode'),
			prop: 'executionMode',
			span: 12,
			value: 'chat',
			component: {
				name: 'el-select',
				options: [
					{ label: t('agent.profile.executionModeChat'), value: 'chat' },
					{ label: t('agent.profile.executionModeWorkflow'), value: 'workflow' }
				]
			}
		},
		{
			label: t('agent.profile.workflowBinding'),
			prop: 'workflowDefinitionId',
			span: 12,
			hidden: ({ scope }: any) => scope?.executionMode !== 'workflow',
			// UI 规范：小字提示图标化，不平铺占用额外空间，消除虚假 prop
			renderLabel: () =>
				h('span', { style: 'display: inline-flex; align-items: center;' }, [
					h('span', t('agent.profile.workflowBinding')),
					h(
						ElTooltip,
						{
							placement: 'top',
							effect: 'dark',
							content: t('agent.profile.workflowBindingHint')
						},
						() =>
							h(
								ElIcon,
								{ style: 'margin-left: 4px; cursor: pointer; color: var(--el-text-color-secondary);' },
								() => h(InfoFilled)
							)
					)
				]),
			component: {
				name: 'el-select',
				options: workflowOptions,
				props: {
					filterable: true,
					clearable: true,
					placeholder: t('agent.profile.workflowBindingPlaceholder')
				}
			}
		}
	],
	onOpen() {
		// 数据防御性初始化（cool-crud-conventions.mdc：多选字段确保为数组）
		const data = Upsert.value?.form;
		if (!data) return;
		if (!Array.isArray(data.tools)) {
			data.tools = [];
		}
	},
	onOpened(data: any) {
		debugProfileId.value = data?.id ?? null;
	}
});

async function openDebug(row: any) {
	debugProfileId.value = row.id;
	debugVisible.value = true;
}

async function openVersions(row: any) {
	versionProfileId.value = row.id;
	versions.value = ((await serviceAgent.versions({ id: row.id })) || []) as any[];
	versionVisible.value = true;
}

async function onRollback(row: any) {
	await ElMessageBox.confirm(t('agent.version.rollbackConfirm', { version: row.version }), t('agent.version.title'), {
		type: 'warning'
	});
	if (!versionProfileId.value) return;
	await serviceAgent.rollback({ id: versionProfileId.value, snapshotId: row.id });
	ElMessage.success(t('agent.profile.rollbackSuccess'));
	versions.value = ((await serviceAgent.versions({ id: versionProfileId.value })) || []) as any[];
}

async function onPublish(row: any) {
	await ElMessageBox.confirm(t('agent.profile.publishConfirm'), t('agent.profile.publish'), {
		type: 'info'
	});
	const res = await serviceAgent.publish({ id: row.id });
	ElMessage.success(`${t('agent.profile.publishSuccess')} v${res.version}`);
	Crud.value?.refresh();
}

async function onToggle(row: any) {
	await serviceAgent.toggleEnabled({ id: row.id, enabled: !row.enabled });
	ElMessage.success(t('agent.profile.toggleSuccess'));
	Crud.value?.refresh();
}
</script>

<style lang="scss" scoped>
.debug-workspace {
	height: 100%;
}

.hash-text {
	font-family: monospace;
	font-size: 12px;
}

.status-tag + .status-tag {
	margin-left: 6px;
}

.name-cell {
	.cell-main {
		line-height: 20px;
	}

	.cell-sub {
		font-size: 12px;
		color: var(--el-text-color-secondary);
		line-height: 18px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
}

.tools-badge {
	cursor: default;
}

.tools-list {
	max-height: 220px;
	overflow: auto;

	.tools-item {
		line-height: 22px;
		font-size: 12px;
	}
}
</style>
