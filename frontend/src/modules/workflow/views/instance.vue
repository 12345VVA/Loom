<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<el-button type="primary" @click="openStartDialog">
				{{ $t('启动测试实例') }}
			</el-button>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索状态、当前节点')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>

	<!-- 启动实例测试弹窗 -->
	<el-dialog
		v-model="startDialog.visible"
		:title="$t('启动工作流实例')"
		width="500px"
		destroy-on-close
	>
		<el-form :model="startDialog.form" label-width="120px">
			<el-form-item :label="$t('工作流定义')" required>
				<el-select
					v-model="startDialog.form.definitionId"
					style="width: 100%"
					@change="onDefinitionChange"
				>
					<el-option
						v-for="item in definitions"
						:key="item.id"
						:label="item.name"
						:value="item.id"
					/>
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('初始输入变量')">
				<cl-editor-codemirror
					v-model="startDialog.form.inputsJson"
					:height="220"
					style="width: 100%"
				/>
			</el-form-item>
		</el-form>
		<template #footer>
			<el-button @click="startDialog.visible = false">{{ $t('取消') }}</el-button>
			<el-button type="primary" :loading="startDialog.loading" @click="submitStartInstance">
				{{ $t('运行') }}
			</el-button>
		</template>
	</el-dialog>

	<!-- 人工确认审批弹窗 -->
	<el-dialog
		v-model="approvalDialog.visible"
		:title="$t('人工审批确认')"
		width="450px"
		destroy-on-close
	>
		<div style="margin-bottom: 16px; color: var(--el-text-color-secondary)">
			{{ $t('该工作流已运行至人工确认节点，请填写反馈并提交以恢复后续节点的执行：') }}
		</div>
		<el-form :model="approvalDialog.form" label-width="80px">
			<el-form-item :label="$t('反馈输入')">
				<el-input
					v-model="approvalDialog.form.userInput"
					type="textarea"
					:rows="4"
					placeholder="例如: true 或 审批通过 的任何变量值"
				/>
			</el-form-item>
		</el-form>
		<template #footer>
			<el-button @click="approvalDialog.visible = false">{{ $t('取消') }}</el-button>
			<el-button type="primary" :loading="approvalDialog.loading" @click="submitApproval">
				{{ $t('提交恢复') }}
			</el-button>
		</template>
	</el-dialog>

	<log-drawer
		v-model:visible="logDrawer.visible"
		:items="logDrawer.items"
		:loading="logDrawer.loading"
		:title="$t('工作流步骤执行日志')"
		size="650px"
		time-format="YYYY-MM-DD HH:mm:ss"
		:empty-text="$t('暂无节点执行步骤记录')"
		@expand-all="expandAllLogs"
		@collapse-all="collapseAllLogs"
	/>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'workflow-instance'
});

import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { ref, reactive, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import LogDrawer from '../components/log-drawer.vue';
import { formatVersionNo } from '../utils';

const { service } = useCool();
const { t } = useI18n();

interface WorkflowDefinition {
	id: number;
	code: string;
	name: string;
	description?: string;
	graphJson?: string;
	isActive: boolean;
	createTime: string;
	updateTime: string;
}

interface WorkflowInstance {
	id: number;
	definitionId: number;
	threadId: string;
	status: 'pending' | 'running' | 'paused' | 'success' | 'failed';
	currentNode?: string;
	stateData: string;
	errorMessage?: string;
	createTime: string;
	updateTime: string;
}

interface WorkflowExecutionLog {
	id: number;
	instanceId: number;
	nodeId: string;
	nodeName: string;
	nodeType: string;
	inputData: string;
	outputData: string;
	latencyMs: number;
	status: 'success' | 'error';
	createTime: string;
	isExpanded?: boolean;
}

const definitions = ref<WorkflowDefinition[]>([]);

// 启动对话框表单
const startDialog = reactive({
	visible: false,
	loading: false,
	form: {
		definitionId: undefined as number | undefined,
		inputsJson: '{\n  "input_query": "关于AI的作文"\n}'
	}
});

// 审批对话框表单
const approvalDialog = reactive({
	visible: false,
	loading: false,
	instanceId: undefined as number | undefined,
	form: {
		userInput: 'true'
	}
});

// 日志抽屉状态
const logDrawer = reactive({
	visible: false,
	loading: false,
	items: [] as WorkflowExecutionLog[]
});

const Table = useTable({
	columns: [
		{ label: t('实例ID'), prop: 'id', width: 90 },
		{ label: t('关联工作流ID'), prop: 'definitionId', width: 130 },
		{
			label: t('版本'),
			prop: 'versionNo',
			width: 100,
			formatter: (_row: any, _col: any, val: any) => formatVersionNo(val)
		},
		{
			label: t('运行时 Thread ID'),
			prop: 'threadId',
			minWidth: 200,
			showOverflowTooltip: true
		},
		{
			label: t('运行状态'),
			prop: 'status',
			width: 120,
			dict: [
				{ label: t('待运行'), value: 'pending', type: 'info' },
				{ label: t('运行中'), value: 'running', type: 'primary' },
				{ label: t('已挂起'), value: 'paused', type: 'warning' },
				{ label: t('成功'), value: 'success', type: 'success' },
				{ label: t('失败'), value: 'failed', type: 'danger' }
			]
		},
		{ label: t('当前激活节点'), prop: 'currentNode', minWidth: 140 },
		{ label: t('错误信息'), prop: 'errorMessage', minWidth: 180, showOverflowTooltip: true },
		{ label: t('累计 Tokens'), prop: 'totalTokens', minWidth: 110 },
		{
			label: t('成本(USD)'),
			prop: 'costUsd',
			minWidth: 110,
			formatter: ({ costUsd }: any) => (costUsd != null ? Number(costUsd).toFixed(4) : '-')
		},
		{ label: t('更新时间'), prop: 'updateTime', sortable: 'desc', minWidth: 170 },
		{
			type: 'op',
			width: 260,
			buttons({ scope }: any) {
				return [
					{
						label: t('执行日志'),
						type: 'primary',
						onClick({ scope }: any) {
							viewExecutionLogs(scope.row);
						}
					},
					{
						label: t('人工确认'),
						type: 'warning',
						hidden: scope.row.status !== 'paused',
						onClick({ scope }: any) {
							openApprovalDialog(scope.row);
						}
					},
					'delete'
				];
			}
		}
	]
});

const Crud = useCrud(
	{
		service: (service as any).workflow.instance
	},
	app => {
		app.refresh();
	}
);

onMounted(() => {
	fetchDefinitions();
});

async function fetchDefinitions() {
	try {
		const list = await (service as any).workflow.definition.list();
		definitions.value = list;
	} catch (e) {
		console.error('Fetch workflow definitions failed', e);
	}
}

async function openStartDialog() {
	startDialog.visible = true;
	startDialog.form.definitionId = undefined;
	startDialog.form.inputsJson = '{}';
	await fetchDefinitions();
}

async function onDefinitionChange(val: number) {
	if (!val) {
		startDialog.form.inputsJson = '{}';
		return;
	}
	try {
		// definition.list 不再返回 graphJson（纯版本表模型），改为 info 取草稿拓扑
		const def = await (service as any).workflow.definition.info({ id: val });
		const graphJson = def.draftGraphJson || def.graphJson;
		if (graphJson) {
			const graph = JSON.parse(graphJson);
			const elements = graph.elements || [];
			const startNode = elements.find((el: any) => el.type === 'start');
			if (startNode && startNode.data?.config?.inputVariables) {
				const vars: string[] = startNode.data.config.inputVariables;
				const inputs: Record<string, string> = {};
				vars.forEach(v => {
					if (v) inputs[v] = '';
				});
				startDialog.form.inputsJson = JSON.stringify(inputs, null, 2);
			} else {
				startDialog.form.inputsJson = '{}';
			}
		} else {
			startDialog.form.inputsJson = '{}';
		}
	} catch (e) {
		console.error('Parse graphJson failed', e);
		ElMessage.error(t('工作流定义数据解析失败'));
		startDialog.form.inputsJson = '{}';
	}
}

async function submitStartInstance() {
	if (!startDialog.form.definitionId) {
		ElMessage.warning(t('请选择要测试的工作流！'));
		return;
	}
	let inputs = {};
	try {
		inputs = JSON.parse(startDialog.form.inputsJson);
	} catch (e) {
		ElMessage.warning(t('初始输入变量 JSON 格式错误！'));
		return;
	}

	startDialog.loading = true;
	try {
		await (service as any).workflow.instance.start({
			definitionId: startDialog.form.definitionId,
			inputs
		});
		ElMessage.success(t('工作流实例启动成功，已加入后台异步执行队列'));
		startDialog.visible = false;
		Crud.value?.refresh();
	} catch (err: any) {
		ElMessage.error(t('启动失败: ') + (err.message || err));
	} finally {
		startDialog.loading = false;
	}
}

function openApprovalDialog(row: WorkflowInstance) {
	approvalDialog.instanceId = row.id;
	approvalDialog.form.userInput = 'true';
	approvalDialog.visible = true;
}

async function submitApproval() {
	if (!approvalDialog.instanceId) return;

	let val: any = approvalDialog.form.userInput;
	// 尝试转换为真布尔值或数额，若报错则以字符串提交
	try {
		if (val.trim() === 'true') val = true;
		else if (val.trim() === 'false') val = false;
		else if (!isNaN(Number(val))) val = Number(val);
		else val = JSON.parse(val);
	} catch (e) {
		// 降级为原始字符串
		val = approvalDialog.form.userInput;
	}

	approvalDialog.loading = true;
	try {
		await (service as any).workflow.instance.resume({
			instanceId: approvalDialog.instanceId,
			userInput: val
		});
		ElMessage.success(t('反馈提交成功，工作流继续运行'));
		approvalDialog.visible = false;
		Crud.value?.refresh();
	} catch (err: any) {
		ElMessage.error(t('恢复失败: ') + (err.message || err));
	} finally {
		approvalDialog.loading = false;
	}
}

async function viewExecutionLogs(row: WorkflowInstance) {
	logDrawer.visible = true;
	logDrawer.loading = true;
	logDrawer.items = [];
	try {
		const list = await (service as any).workflow.instance.logs({ instanceId: row.id });
		logDrawer.items = list.map((item: any, index: number) => ({
			...item,
			isExpanded: item.status !== 'success' || index === list.length - 1
		}));
	} catch (err: any) {
		ElMessage.error(t('获取执行日志失败: ') + (err.message || err));
	} finally {
		logDrawer.loading = false;
	}
}

function expandAllLogs() {
	logDrawer.items.forEach(item => {
		item.isExpanded = true;
	});
}

function collapseAllLogs() {
	logDrawer.items.forEach(item => {
		item.isExpanded = false;
	});
}
</script>
