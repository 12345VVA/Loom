<template>
	<div class="workflow-editor-container">
		<!-- 主画布区 -->
		<div class="editor-body">
			<!-- 画布中央 -->
			<div
				class="canvas-wrapper"
				:class="{ 'has-config-panel': !!selectedNode }"
				@drop="onDrop"
				@dragover.prevent="onCanvasDragOver"
				@dragleave="onCanvasDragLeave"
				@contextmenu.prevent
			>
				<vue-flow
					v-model="elements"
					:node-types="nodeTypes as any"
					:edge-types="edgeTypes as any"
					:default-edge-options="defaultEdgeOptions"
					:pan-on-scroll="true"
					:snap-to-grid="true"
					:snap-grid="[20, 20]"
					:selection-on-drag="true"
					@connect="onConnect"
					@pane-ready="onPaneReady"
					@node-click="onNodeClick"
					@pane-click="onPaneClick"
					@node-context-menu="onNodeContextMenu"
					@pane-context-menu="onPaneContextMenu"
					@edge-context-menu="onEdgeContextMenu"
					@node-drag="onNodeDrag"
					@node-drag-stop="onNodeDragStop"
				>
					<background pattern-color="#e0e0e0" :gap="16" />
					<controls position="bottom-right" />
					<mini-map v-if="miniMapVisible" />
					<!-- 对齐辅助线 -->
					<svg
						v-if="guides.length"
						class="alignment-guides"
						style="
							position: absolute;
							top: 0;
							left: 0;
							width: 100%;
							height: 100%;
							pointer-events: none;
							z-index: 4;
						"
					>
						<line
							v-for="(g, i) in guides"
							:key="i"
							:x1="g.type === 'vertical' ? g.position : 0"
							:y1="g.type === 'horizontal' ? g.position : 0"
							:x2="g.type === 'vertical' ? g.position : 99999"
							:y2="g.type === 'horizontal' ? g.position : 99999"
							stroke="var(--el-color-primary)"
							stroke-width="1"
							stroke-dasharray="4 3"
							opacity="0.5"
						/>
					</svg>
					<editor-bottom-toolbar
						:has-incomplete-nodes="hasIncompleteNodes"
						:workflow-name="workflowName"
						:workflow-code="workflowCode"
						:test-log-drawer-instance-id="testLogDrawer.instanceId"
						:saving="saving"
						:panel-open="!!selectedNode"
						:panel-width="configPanelWidth"
						:can-undo="canUndo"
						:can-redo="canRedo"
						@drag-start="onDragStart"
						@add-node="onAddNodeClick"
						@open-test-dialog="openTestDialog"
						@clear-test-status="clearTestStatus"
						@reopen-test-log-drawer="reopenTestLogDrawer"
						@export-workflow="exportWorkflow"
						@save-workflow="saveWorkflow"
						@publish-workflow="publishWorkflow"
						@undo="undo()"
						@redo="redo()"
					/>
				</vue-flow>

				<!-- MiniMap 显隐切换（#28） -->
				<el-tooltip
					:content="miniMapVisible ? $t('隐藏缩略图') : $t('显示缩略图')"
					placement="right"
				>
					<el-button class="minimap-toggle" circle :icon="Grid" @click="toggleMiniMap" />
				</el-tooltip>

				<!-- 右键上下文菜单（组件化，键盘 a11y 在组件内） -->
				<context-menu
					:visible="contextMenu.visible"
					:x="contextMenu.x"
					:y="contextMenu.y"
					:can-test="canTestContextNode"
					:can-distribute="canDistribute"
					@close="closeContextMenu"
					@edit="editContextNode"
					@test="testContextNode"
					@duplicate="duplicateNode"
					@distribute-h="distributeHorizontal"
					@distribute-v="distributeVertical"
					@delete="deleteContextNode"
				/>

				<!-- 半透明遮罩 -->
				<transition name="panel-backdrop">
					<div
						v-if="selectedNode"
						class="config-panel-backdrop"
						@click="selectedNodeId = null"
						@contextmenu.prevent="selectedNodeId = null"
					/>
				</transition>

				<!-- 浮层配置面板（滑入动画） -->
				<transition name="config-panel-slide">
					<node-config-panel
						v-if="selectedNode"
						:selected-node="selectedNode"
						:upstream-variables="upstreamVariables"
						:variable-syntax-hints="variableSyntaxHints"
						:available-target-nodes="availableTargetNodes"
						:filtered-body-target-nodes="availableTargetNodes"
						:ai-profiles="aiProfiles"
						:workflow-id="workflowId || undefined"
						@delete="deleteSelectedNode"
						@update:width="(w: number) => (configPanelWidth = w)"
						@close="selectedNodeId = null"
					/>
				</transition>

				<!-- 首次使用引导 -->
				<transition name="empty-hint-fade">
					<div v-if="!selectedNode && elements.length <= 2" class="canvas-empty-hint">
						<el-icon class="empty-hint-icon"><info-filled /></el-icon>
						<span class="empty-hint-text">{{ emptyHintTitle }}</span>
						<span class="empty-hint-sub">{{ emptyHintSub }}</span>
						<div class="empty-hint-arrow">
							<el-icon class="bounce-arrow"><arrow-down /></el-icon>
						</div>
					</div>
				</transition>
			</div>
		</div>

		<!-- 测试运行初始变量弹窗 -->
		<el-dialog
			v-model="testDialog.visible"
			:title="$t('测试运行工作流')"
			width="500px"
			destroy-on-close
		>
			<el-form :model="testDialog.form" label-width="120px">
				<el-form-item :label="$t('初始输入变量')">
					<cl-editor-codemirror v-model="testDialog.form.inputsJson" :height="220" />
				</el-form-item>
			</el-form>
			<template #footer>
				<el-button @click="testDialog.visible = false">{{ $t('取消') }}</el-button>
				<el-button type="success" :loading="testDialog.loading" @click="startTestRun">
					{{ $t('运行') }}
				</el-button>
			</template>
		</el-dialog>

		<!-- 单节点测试弹窗 -->
		<el-dialog
			v-model="nodeTestDialog.visible"
			:title="$t('测试节点') + '：' + nodeTestDialog.nodeLabel"
			width="500px"
			destroy-on-close
		>
			<el-form :model="nodeTestDialog.form" label-width="120px" label-position="top">
				<el-form-item :label="$t('模拟上游输入变量')">
					<cl-editor-codemirror v-model="nodeTestDialog.form.inputsJson" :height="260" />
				</el-form-item>
			</el-form>

			<!-- 测试结果展示区 -->
			<div v-if="nodeTestDialog.result" class="node-test-result">
				<div class="node-test-result__header">
					<el-tag
						v-if="nodeTestDialog.result.status === 'success'"
						type="success"
						size="small"
						>{{ $t('运行成功') }}</el-tag
					>
					<el-tag v-else type="danger" size="small">{{ $t('运行失败') }}</el-tag>
					<span v-if="nodeTestDialog.result.timeCost" class="node-test-result__time">
						{{ nodeTestDialog.result.timeCost }}ms
					</span>
				</div>
				<div v-if="nodeTestDialog.result.error" class="node-test-result__error">
					{{ nodeTestDialog.result.error }}
				</div>
				<div class="node-test-result__section">
					<div class="node-test-result__label">{{ $t('执行输出') }}</div>
					<pre class="node-test-result__output">{{
						formatJson(nodeTestDialog.result.outputData)
					}}</pre>
				</div>
			</div>

			<template #footer>
				<el-button @click="closeNodeTestDialog">{{ $t('关闭') }}</el-button>
				<el-button type="success" :loading="nodeTestDialog.loading" @click="startNodeTest">
					{{ $t('运行测试') }}
				</el-button>
			</template>
		</el-dialog>

		<log-drawer
			v-model:visible="testLogDrawer.visible"
			:items="testLogDrawer.items"
			:loading="testLogDrawer.loading"
			:status="testLogDrawer.status"
			:title="$t('测试运行日志')"
			size="500px"
			:empty-text="$t('暂无执行记录，等待后端运行')"
			@close="stopLogPolling"
			@expand-all="expandAllTestLogs"
			@collapse-all="collapseAllTestLogs"
		/>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'workflow-editor'
});

import {
	ref,
	onMounted,
	onActivated,
	onDeactivated,
	onBeforeUnmount,
	computed,
	watch,
	provide
} from 'vue';
import { useRoute, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import { useCool } from '/@/cool';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';

// 导入 Vue Flow
import { VueFlow, useVueFlow } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';
import '@vue-flow/minimap/dist/style.css';

// 导入 Element Plus 图标
import { ArrowDown, Grid } from '@element-plus/icons-vue';

// Vue Flow 样式文件
import '@vue-flow/core/dist/style.css';
import '@vue-flow/core/dist/theme-default.css';
import '@vue-flow/controls/dist/style.css';

import { formatJson, isRequiredConfigMissing } from '../utils';
import type { FlowNode, FlowEdge } from '../types/editor';
import { migrateLoadedElements } from '../utils/graph-migration';
import { hitTestGroup } from '../utils/group-hit-test';
import LogDrawer from '../components/log-drawer.vue';
import { OPEN_NODE_TEST_DIALOG_KEY } from '../components/constants';
import dayjs from 'dayjs';

import { useWorkflowTest } from '../composables/useWorkflowTest';
import { useAlignmentGuides } from '../composables/useAlignmentGuides';
import { useUndoRedo } from '../composables/useUndoRedo';
import { useNodeTest } from '../composables/useNodeTest';
import { useGraphBuilder } from '../composables/useGraphBuilder';
import { useSaveFlow } from '../composables/useSaveFlow';
import { useUpstreamVariables } from '../composables/useUpstreamVariables';
import { useContextMenu } from '../composables/useContextMenu';
import { useNodeFactory } from '../composables/useNodeFactory';
import { useEdgeConnect } from '../composables/useEdgeConnect';
import { planNodeRemoval } from '../composables/useNodeOps';

// 导入重构的子组件
import NodeConfigPanel from '../components/node-config-panel.vue';
import EditorBottomToolbar from '../components/editor-bottom-toolbar.vue';
import StartNode from '../components/custom-nodes/start-node.vue';
import EndNode from '../components/custom-nodes/end-node.vue';
import LlmNode from '../components/custom-nodes/llm-node.vue';
import ToolNode from '../components/custom-nodes/tool-node.vue';
import ConditionNode from '../components/custom-nodes/condition-node.vue';
import SwitchNode from '../components/custom-nodes/switch-node.vue';
import HumanInputNode from '../components/custom-nodes/human-input-node.vue';
import IntentClassifierNode from '../components/custom-nodes/intent-classifier-node.vue';
import LoopControllerNode from '../components/custom-nodes/loop-controller-node.vue';
import BatchProcessorNode from '../components/custom-nodes/batch-processor-node.vue';
import ImageGeneratorNode from '../components/custom-nodes/image-generator-node.vue';
import ToolExecutorNode from '../components/custom-nodes/tool-executor-node.vue';
import LoopBodyGroupNode from '../components/custom-nodes/loop-body-group-node.vue';
import VariableAssignmentNode from '../components/custom-nodes/variable-assignment-node.vue';
import VariableTransformNode from '../components/custom-nodes/variable-transform-node.vue';
import LabelEdge from '../components/custom-edges/label-edge.vue';
import ContextMenu from '../components/context-menu.vue';

const { service } = useCool();
const { t } = useI18n();
const route = useRoute();

const { project, getSelectedNodes } = useVueFlow();

const { guides, computeGuides, clearGuides } = useAlignmentGuides();

// 注册自定义节点组件
const nodeTypes = {
	start: StartNode,
	end: EndNode,
	llm: LlmNode,
	tool: ToolNode,
	condition: ConditionNode,
	switch: SwitchNode,
	human_input: HumanInputNode,
	intent_classifier: IntentClassifierNode,
	loop_controller: LoopControllerNode,
	batch_processor: BatchProcessorNode,
	image_generator: ImageGeneratorNode,
	tool_executor: ToolExecutorNode,
	loop_body_group: LoopBodyGroupNode,
	variable_assignment: VariableAssignmentNode,
	variable_transform: VariableTransformNode
};

// 注册自定义边组件
const edgeTypes = { label: LabelEdge };

// 提供获取 elements 的方法给子组件
provide('getElements', () => elements.value);

const workflowId = ref<string | null>(null);
const workflowName = ref('');
const workflowCode = ref('');
const workflowDescription = ref('');
const saving = ref(false);
const selectedNodeId = ref<string | null>(null);
const isDirty = ref(false);
const configPanelWidth = ref(420);
const loaded = ref(false);

// MiniMap 显隐（#28）：localStorage 持久化，默认显示
const miniMapVisible = ref(localStorage.getItem('loom_editor_minimap_visible') !== 'false');
function toggleMiniMap() {
	miniMapVisible.value = !miniMapVisible.value;
	localStorage.setItem('loom_editor_minimap_visible', String(miniMapVisible.value));
}

// 右键菜单的键盘导航（a11y）与打开聚焦已随 context-menu.vue 组件化迁移

onBeforeUnmount(() => {
	stopLogPolling();
	window.removeEventListener('keydown', handleKeyDown);
});

// 可配置大模型配置列表
const aiProfiles = ref<Eps.profile[]>([]);

// 节点元素集合，包括 Nodes 和 Edges
const elements = ref<(FlowNode | FlowEdge)[]>([]);

let _persistSig = '';

// 右键菜单状态与开/关（键盘 a11y 在 context-menu.vue 组件内）
const { contextMenu, canTestContextNode, canDistribute, openContextMenu, closeContextMenu } =
	useContextMenu(elements, getSelectedNodes);

const { canUndo, canRedo, pushSnapshot, undo, redo, init: initUndoRedo } = useUndoRedo(elements);

// 节点添加 / 标签 / 输出变量名生成（默认 config 数据表见 utils/node-default-configs.ts）
const { handleAddNode, duplicateNode: duplicateNodeImpl } = useNodeFactory(
	elements,
	t,
	pushSnapshot
);

// 画布连线校验与边生成（标签推导见 utils/edge-label.ts）
const { onConnect } = useEdgeConnect(elements, t, pushSnapshot);

// 图构建（buildGraphPayload / persistSignature）抽离为 composable，便于单元测试
const { persistSignature, buildGraphPayload } = useGraphBuilder(elements);

// 保存逻辑（saveWorkflow + 拓扑校验 validateGraph）抽离为 composable，便于单元测试
const { saveWorkflow } = useSaveFlow({
	elements,
	saving,
	isDirty,
	workflowId,
	workflowCode,
	workflowName,
	workflowDescription,
	service,
	buildGraphPayload,
	persistSignature,
	// 保存成功后重置 isDirty 基线签名（_persistSig 与 watch 共享）
	onSaved: sig => {
		_persistSig = sig;
	}
});

// 测试运行相关方法使用 composable
const {
	testDialog,
	testLogDrawer,
	clearTestStatus,
	reopenTestLogDrawer,
	openTestDialog,
	startTestRun,
	stopLogPolling,
	expandAllTestLogs,
	collapseAllTestLogs
} = useWorkflowTest(service, t, workflowId, isDirty, elements, saveWorkflow);

// 上游变量收集（start 输入变量、节点 outputVariable、循环上下文变量）+ 版本缓存
// 已抽离至 composables/useUpstreamVariables.ts，便于单元测试。
const { getUpstreamVariablesForNode, upstreamVariablesOf, invalidateUpstreamCache } =
	useUpstreamVariables(elements);

// 单节点测试 composable
const { nodeTestDialog, openNodeTestDialog, startNodeTest, closeNodeTestDialog, clearMockCache } =
	useNodeTest(
		service,
		t,
		workflowId,
		isDirty,
		elements,
		saveWorkflow,
		getUpstreamVariablesForNode
	);

// 监听测试抽屉打开，如果打开则关闭配置面板
watch(
	() => testLogDrawer.visible,
	val => {
		if (val) {
			selectedNodeId.value = null;
		}
	}
);

// 定义画布连线的默认样式
const defaultEdgeOptions = {
	animated: true,
	style: { stroke: '#409eff', strokeWidth: 2 }
};

// 当前选中节点的计算属性
const selectedNode = computed(() => {
	if (!selectedNodeId.value) return null;
	return elements.value.find(el => el.id === selectedNodeId.value && !('source' in el)) as
		| FlowNode
		| undefined;
});

// 除了自身之外的可用目标节点（用于分支设置的路由下拉菜单中）
const availableTargetNodes = computed(() => {
	return elements.value.filter(
		el => !('source' in el) && el.id !== selectedNodeId.value
	) as FlowNode[];
});

// 是否存在必填配置缺失的节点（驱动工具栏“未完成节点”提示）
const hasIncompleteNodes = computed(() => {
	return elements.value.some((el: any) => !('source' in el) && isRequiredConfigMissing(el));
});

// 收集当前选中节点的上游可达变量（带版本缓存，逻辑见 useUpstreamVariables）
const upstreamVariables = computed(() => upstreamVariablesOf(selectedNode.value?.id));

// 变量引用格式提示
const variableSyntaxHints = computed(() => {
	const nodeType = selectedNode.value?.type;
	if (!nodeType) return [];
	const hints: { label: string; syntax: string }[] = [];
	if (['llm', 'image_generator', 'end'].includes(nodeType)) {
		hints.push({ label: '提示词插值', syntax: '{变量名}' });
		hints.push({ label: '嵌套访问', syntax: '{变量名.字段名}' });
	}
	if (['condition'].includes(nodeType)) {
		hints.push({ label: '条件表达式', syntax: 'variables.变量名' });
	}
	if (['tool_executor'].includes(nodeType)) {
		hints.push({ label: 'JSON 参数', syntax: 'variables.变量名' });
	}
	return hints;
});

// 空状态引导文案（根据当前节点数量动态调整）
const emptyHintTitle = computed(() => {
	if (elements.value.length === 0) {
		return t('从下方工具栏拖入节点开始构建工作流');
	}
	return t('点击节点以编辑配置');
});
// 空状态引导副标题（根据当前节点数量动态调整）
const emptyHintSub = computed(() => {
	if (elements.value.length === 0) {
		return t('将节点拖拽到画布，拖拽连线构建工作流');
	}
	return t('拖拽连线或添加 LLM 节点来处理用户请求');
});

onMounted(() => {
	workflowId.value = (route.query.id as string) || null;
	if (workflowId.value) {
		fetchWorkflowData();
	} else {
		loaded.value = true;
		initUndoRedo();
		// 加载/新建完成：以当前拓扑签名（已剥离运行态字段）作为 isDirty 比较基线
		_persistSig = persistSignature(elements.value);
	}
	fetchAiProfiles();
	// 键盘监听改由 onActivated/onDeactivated 配对管理（keep-alive 下 onMounted 仅首次触发）
});

// keep-alive 缓存复用：激活时确保键盘监听在位；切换到不同工作流（route.query.id 变化）时重置画布并重新加载，
// 避免残留上一个工作流的拓扑。同一工作流来回切换则保留编辑状态（缓存的正常价值）。
onActivated(() => {
	// 激活时注册键盘监听（离开页面由 onDeactivated 注销，避免在别的页面误触 Ctrl+S/Delete）
	window.addEventListener('keydown', handleKeyDown);
	const currentId = (route.query.id as string) || null;
	if (currentId === workflowId.value) return;
	// 切换到不同工作流：清脏标记（旧工作流未保存编辑已在路由守卫确认放弃），新工作流按干净状态加载
	isDirty.value = false;
	// 清空与具体工作流绑定的临时状态
	selectedNodeId.value = null;
	contextMenu.visible = false;
	clearTestStatus();
	workflowId.value = currentId;
	if (currentId) {
		fetchWorkflowData();
	} else {
		// 新建工作流：清空画布至初始空拓扑
		elements.value = [];
		loaded.value = true;
		initUndoRedo();
		_persistSig = persistSignature(elements.value);
	}
	fetchAiProfiles();
});

// 停用时注销键盘监听（keep-alive 下 onBeforeUnmount 不触发，用 onDeactivated 配对管理）
onDeactivated(() => {
	window.removeEventListener('keydown', handleKeyDown);
	// 切出页面时一并停止试运行 SSE 流与重连/防抖定时器：useWorkflowTest 持有 stream.invoke +
	// reconnectTimer + logRefreshTimer 三个副作用，keep-alive 下 onBeforeUnmount 不会触发，
	// 仅清 keydown 会让它们在后台继续空跑（多次进出还会叠加多个 SSE 连接）
	stopLogPolling();
});

// 未保存修改时，离开编辑器或切换工作流前提示，避免误丢编辑
async function confirmDiscardIfDirty(): Promise<boolean> {
	if (!isDirty.value) return true;
	try {
		await ElMessageBox.confirm(
			t('当前工作流有未保存的修改，继续将丢弃这些修改。'),
			t('未保存提示'),
			{ type: 'warning', confirmButtonText: t('放弃修改'), cancelButtonText: t('取消') }
		);
		return true;
	} catch {
		return false;
	}
}

// 离开编辑器到其他页面
onBeforeRouteLeave(async () => {
	if (!(await confirmDiscardIfDirty())) return false;
});

// 同组件切换工作流（/editor?id=A → /editor?id=B）
onBeforeRouteUpdate(async to => {
	if (String(to.query.id ?? '') !== String(route.query.id ?? '')) {
		if (!(await confirmDiscardIfDirty())) return false;
	}
});

// 全局键盘快捷键：Esc 关闭面板/菜单、Ctrl+S 保存、Ctrl+Z/Shift+Z 撤销/重做、Delete/Backspace 删除选中元素
function handleKeyDown(event: KeyboardEvent) {
	// 如果用户正在输入框/文本域中打字，则忽略快捷键删除
	const activeEl = document.activeElement;
	if (
		activeEl &&
		(activeEl.tagName === 'INPUT' ||
			activeEl.tagName === 'TEXTAREA' ||
			activeEl.hasAttribute('contenteditable'))
	) {
		return;
	}

	if (event.key === 'Escape') {
		selectedNodeId.value = null;
		closeContextMenu();
	}

	if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
		event.preventDefault();
		saveWorkflow();
	}

	if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
		event.preventDefault();
		if (event.shiftKey) {
			if (redo()) ElMessage.info(t('已重做'));
		} else {
			if (undo()) ElMessage.info(t('已撤销'));
		}
	}

	if (event.key === 'Delete' || event.key === 'Backspace') {
		deleteSelectedElements();
	}
}

// 统一删除入口：级联清理关联 group + 子节点坐标转换、清理测试缓存、选中态复位、记录撤销快照。
// 供多选删除 / 右键删除 / 配置面板删除复用，确保所有删除路径都进入撤销栈。
function removeNodes(nodeIds: string[], edgeIds: string[] = []): boolean {
	if (nodeIds.length === 0 && edgeIds.length === 0) return false;
	// 级联清理关联 group + 子节点坐标转换（planNodeRemoval）
	elements.value = planNodeRemoval(elements.value, { nodeIds, edgeIds });
	clearMockCache(nodeIds);
	if (selectedNodeId.value && nodeIds.includes(selectedNodeId.value)) {
		selectedNodeId.value = null;
	}
	pushSnapshot();
	return true;
}

// 删除画布上当前选中的节点与边（含关联 group 的级联清理）
function deleteSelectedElements() {
	const nodesToRemove = elements.value.filter(el => !('source' in el) && (el as any).selected);
	const edgesToRemove = elements.value.filter(el => 'source' in el && (el as any).selected);

	if (removeNodes(nodesToRemove.map(n => n.id), edgesToRemove.map(e => e.id))) {
		ElMessage.success(t('已删除所选元素'));
	}
}

watch(
	elements,
	() => {
		// 仅当"非运行态"字段变化时才视为脏：试运行/单节点测试写入的 class、runLog
		// 不触发保存按钮，也不清空上游缓存（运行态不改变拓扑与上游输出）
		const sig = persistSignature(elements.value);
		if (sig === _persistSig) return;
		_persistSig = sig;
		invalidateUpstreamCache();
		if (loaded.value) {
			isDirty.value = true;
		}
	},
	{ deep: true, flush: 'post' }
);

// 拉取工作流详情并还原画布拓扑：解析草稿 JSON、兼容旧版字段/handle 格式迁移；无草稿时初始化默认开始-结束节点
async function fetchWorkflowData() {
	try {
		const res = await (service as any).workflow.definition.info({ id: workflowId.value });
		workflowName.value = res.name;
		workflowCode.value = res.code;
		workflowDescription.value = res.description || '';

		// 加载草稿拓扑（纯版本表模型：graph 存版本表，info 回填 draftGraphJson）
		if (res.draftGraphJson && res.draftGraphJson !== '{}') {
			const graph = JSON.parse(res.draftGraphJson);

			// 加载后字段迁移/适配（纯函数，见 utils/graph-migration.ts）：
			// 仅保留 tool_executor arguments→argumentsJson 编辑态适配、switch/intent 稳定 id 补全。
			// 旧版本兼容（默认值补全、sourceHandle 下标/反向重建）已激进清理。
			const loadedElements = migrateLoadedElements(graph.elements || []);

			elements.value = loadedElements;
		} else {
			// 初始化一个"开始"和"结束"的默认节点
			elements.value = [
				{
					id: 'node_start',
					type: 'start',
					label: t('开始'),
					position: { x: 100, y: 150 },
					data: { config: { inputVariables: ['query'] } }
				},
				{
					id: 'node_end',
					type: 'end',
					label: t('结束'),
					position: { x: 600, y: 150 },
					data: { config: { outputFormat: 'json', outputFields: [] } }
				}
			];
		}
		loaded.value = true;
		initUndoRedo();
		// 加载/新建完成：以当前拓扑签名（已剥离运行态字段）作为 isDirty 比较基线
		_persistSig = persistSignature(elements.value);
	} catch (e) {
		ElMessage.error(t('获取工作流详情失败'));
	}
}

// 拉取可配置的大模型列表，供 LLM/图像生成等节点选择模型
async function fetchAiProfiles() {
	try {
		const list = await (service as any).ai.profile.list({});
		aiProfiles.value = list;
	} catch (e) {
		console.error('Fetch AI profiles failed', e);
	}
}

// 侧边栏拖拽开始记录节点类型
function onDragStart(event: DragEvent, type: string) {
	if (event.dataTransfer) {
		event.dataTransfer.setData('application/vueflow', type);
		event.dataTransfer.effectAllowed = 'move';
	}
}

// handleAddNode 与默认 config 构建已迁移至 useNodeFactory composable

// 通过点击面板添加节点
function onAddNodeClick(type: string) {
	// 获取画布中心
	const wrapper = document.querySelector('.vue-flow');
	if (!wrapper) return;
	const rect = wrapper.getBoundingClientRect();

	const centerX = rect.width / 2;
	const centerY = rect.height / 2;

	// 投影到 vue-flow 坐标系
	const pos = project({ x: centerX, y: centerY });
	handleAddNode(type, pos.x - 50, pos.y - 20);
}

// 画布放置时实例化新节点
function onDrop(event: DragEvent) {
	const type = event.dataTransfer?.getData('application/vueflow');
	if (!type) return;

	// 计算在画布内的放置坐标
	const react = event.currentTarget as HTMLElement;
	const bounds = react.getBoundingClientRect();

	// 首先投影鼠标所在的真实屏幕相对坐标
	const projected = project({
		x: event.clientX - bounds.left,
		y: event.clientY - bounds.top
	});

	// 在 VueFlow 坐标系中减去节点的半宽和半高，使其在鼠标居中
	handleAddNode(type, projected.x - 50, projected.y - 20);
}

// getTypeName / getNextLabel / sanitizeLabel / getUniqueOutputVar 已迁移至 useNodeFactory composable

// onConnect / getEdgeLabel 已迁移至 useEdgeConnect composable 与 utils/edge-label.ts

// 画布就绪：自适应缩放使全部节点可见
function onPaneReady(instance: any) {
	instance.fitView();
}

// 点击节点：选中该节点并打开配置面板，同时关闭右键菜单
function onNodeClick(event: { node: any }) {
	selectedNodeId.value = event.node.id;
	contextMenu.visible = false;
}

// 点击画布空白：取消选中节点并关闭右键菜单
function onPaneClick() {
	selectedNodeId.value = null;
	contextMenu.visible = false;
}

// 画布 dragover：group 容器拖入高亮
function onCanvasDragOver(event: DragEvent) {
	document
		.querySelectorAll('.loop-body-group-node.is-drag-over')
		.forEach(el => el.classList.remove('is-drag-over'));
	const type = event.dataTransfer?.getData('application/vueflow');
	if (!type || type === 'loop_body_group') return;

	const canvasEl = document.querySelector('.canvas-wrapper');
	if (!canvasEl) return;
	const bounds = canvasEl.getBoundingClientRect();
	const flowX = event.clientX - bounds.left;
	const flowY = event.clientY - bounds.top;

	// 命中判定见 utils/group-hit-test.ts
	const hit = hitTestGroup(elements.value, flowX, flowY);
	if (hit) {
		const domNode = document.querySelector(`[data-id="${hit.id}"] .loop-body-group-node`);
		if (domNode) domNode.classList.add('is-drag-over');
	}
}

// 拖拽离开画布：清除所有 group 容器的高亮态
function onCanvasDragLeave() {
	document
		.querySelectorAll('.loop-body-group-node.is-drag-over')
		.forEach(el => el.classList.remove('is-drag-over'));
}

// 节点拖动对齐辅助线
function onNodeDrag(event: any) {
	const dragNode = event.node;
	if (!dragNode) return;
	const allNodes = elements.value.filter(el => !('source' in el)) as FlowNode[];
	computeGuides(dragNode.id, dragNode.position, allNodes);
}

// 节点拖拽结束：清除对齐辅助线并记录撤销快照
function onNodeDragStop() {
	clearGuides();
	pushSnapshot();
}

// 右键节点：打开上下文菜单（边界回弹逻辑在 useContextMenu 内）
function onNodeContextMenu(event: any) {
	event.event?.preventDefault();
	const node = event.node;
	if (!node) return;
	openContextMenu(node.id, event.event?.clientX || 0, event.event?.clientY || 0);
}

// 画布空白右键：阻止浏览器默认菜单并关闭已有右键菜单
function onPaneContextMenu(event: any) {
	(event?.event ?? event)?.preventDefault?.();
	closeContextMenu();
}

// 连线右键：阻止浏览器默认菜单并关闭已有右键菜单
function onEdgeContextMenu(event: any) {
	(event?.event ?? event)?.preventDefault?.();
	closeContextMenu();
}

// 右键菜单“配置节点”：选中目标节点并打开配置面板
function editContextNode() {
	selectedNodeId.value = contextMenu.nodeId;
	closeContextMenu();
}

// canTestContextNode / canDistribute 已迁移至 useContextMenu composable

// 水平等距分布：以最左/最右节点为界，等间距重排中间节点的 x 坐标
function distributeHorizontal() {
	const selected = getSelectedNodes.value as FlowNode[];
	if (selected.length < 3) return;
	selected.sort((a, b) => a.position.x - b.position.x);
	const minX = selected[0].position.x;
	const maxX = selected[selected.length - 1].position.x;
	const step = (maxX - minX) / (selected.length - 1);
	selected.forEach((node, i) => {
		if (i > 0 && i < selected.length - 1) {
			node.position.x = minX + step * i;
		}
	});
	pushSnapshot();
	closeContextMenu();
}

// 垂直等距分布：以最上/最下节点为界，等间距重排中间节点的 y 坐标
function distributeVertical() {
	const selected = getSelectedNodes.value as FlowNode[];
	if (selected.length < 3) return;
	selected.sort((a, b) => a.position.y - b.position.y);
	const minY = selected[0].position.y;
	const maxY = selected[selected.length - 1].position.y;
	const step = (maxY - minY) / (selected.length - 1);
	selected.forEach((node, i) => {
		if (i > 0 && i < selected.length - 1) {
			node.position.y = minY + step * i;
		}
	});
	pushSnapshot();
	closeContextMenu();
}

// 向子组件（base-node、node-config-panel 等）提供单节点测试弹窗的打开方法
provide(OPEN_NODE_TEST_DIALOG_KEY, openNodeTestDialog);

// 单节点测试：右键菜单适配层（状态管理已迁移至 useNodeTest composable）
async function testContextNode() {
	if (!canTestContextNode.value) {
		ElMessage.warning(t('该类型节点不支持单独测试'));
		return;
	}
	closeContextMenu();
	await openNodeTestDialog(contextMenu.nodeId);
}

// 复制右键节点（复制逻辑见 useNodeFactory.duplicateNode，此处仅负责关闭菜单）
function duplicateNode() {
	duplicateNodeImpl(contextMenu.nodeId);
	closeContextMenu();
}

// 右键菜单“删除节点”：走统一删除入口
function deleteContextNode() {
	if (removeNodes([contextMenu.nodeId])) {
		ElMessage.success(t('已删除节点'));
	}
	closeContextMenu();
}

// 配置面板“删除”按钮：走统一删除入口（含撤销快照，修复此前配置面板删除无法 Ctrl+Z 撤销）
function deleteSelectedNode() {
	if (!selectedNodeId.value) return;
	removeNodes([selectedNodeId.value]);
}

// saveWorkflow + 拓扑校验（validateGraph）已抽离至 composables/useSaveFlow.ts

// 发布草稿：先保存最新草稿，再 publish（一步上线；运行中实例按其版本继续跑、不受影响）
async function publishWorkflow() {
	if (!workflowId.value) return;
	try {
		await ElMessageBox.confirm(
			t(
				'发布后新启动的实例将使用此版本，正在运行的实例按其版本继续跑、不受影响。是否先保存并发布？'
			),
			t('发布'),
			{ type: 'warning' }
		);
	} catch {
		return; // 用户取消
	}
	const saved = await saveWorkflow();
	if (!saved) return;
	try {
		await (service as any).workflow.version.publish({ definitionId: Number(workflowId.value) });
		ElMessage.success(t('发布成功'));
		await fetchWorkflowData();
	} catch (err: any) {
		ElMessage.error(t('发布失败: ') + (err.message || err));
	}
}

// 导出工作流
function exportWorkflow() {
	if (!workflowId.value) return;

	const exportData = {
		version: '1.0',
		type: 'LoomWorkflow',
		metadata: {
			name: workflowName.value,
			description: workflowDescription.value
		},
		graph_json: JSON.stringify(buildGraphPayload())
	};

	const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	const dateStr = dayjs().format('YYYYMMDD');
	a.download = `LoomWorkflow_${workflowName.value || 'Untitled'}_${dateStr}.json`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);

	ElMessage.success(t('导出成功'));
}
</script>

<style lang="scss" scoped>
.workflow-editor-container {
	display: flex;
	flex-direction: column;
	width: 100%;
	height: calc(100vh - 100px);
	background-color: #fafafa;
	overflow: hidden;
}

.editor-body {
	display: flex;
	flex: 1;
	width: 100%;
	overflow: hidden;
}

.canvas-wrapper {
	flex: 1;
	height: 100%;
	position: relative;
	background-color: #f7f9fb;
	overflow: hidden;
}

.minimap-toggle {
	position: absolute;
	top: 16px;
	left: 16px;
	z-index: 5;
	background: rgba(255, 255, 255, 0.85);
	backdrop-filter: blur(8px);
}

// 半透明遮罩
.config-panel-backdrop {
	position: absolute;
	inset: 0;
	background: rgba(0, 0, 0, 0.08);
	z-index: 8;
	cursor: pointer;
}
.panel-backdrop-enter-active,
.panel-backdrop-leave-active {
	transition: opacity 0.25s ease;
}
.panel-backdrop-enter-from,
.panel-backdrop-leave-to {
	opacity: 0;
}

// 配置面板滑入/出动画
.config-panel-slide-enter-active,
.config-panel-slide-leave-active {
	transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.config-panel-slide-enter-from,
.config-panel-slide-leave-to {
	transform: translateX(100%);
}

// 首次使用引导
.canvas-empty-hint {
	position: absolute;
	top: 50%;
	left: 50%;
	transform: translate(-50%, -50%);
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: var(--wf-space-sm);
	pointer-events: none;
	user-select: none;
	z-index: 3;

	.empty-hint-icon {
		font-size: 32px;
		color: var(--el-text-color-placeholder);
		opacity: 0.35;
	}
	.empty-hint-text {
		font-size: 14px;
		color: var(--el-text-color-secondary);
		font-weight: 500;
	}
	.empty-hint-sub {
		font-size: 12px;
		color: var(--el-text-color-placeholder);
	}
	.empty-hint-arrow {
		margin-top: 4px;
		.bounce-arrow {
			font-size: 20px;
			color: var(--el-color-primary);
			animation: wf-bounce-arrow 1.5s ease-in-out infinite;
		}
	}
}
.empty-hint-fade-enter-active,
.empty-hint-fade-leave-active {
	transition: opacity 0.3s ease;
}
.empty-hint-fade-enter-from,
.empty-hint-fade-leave-to {
	opacity: 0;
}

// 单节点测试结果展示
.node-test-result {
	margin-top: 12px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	overflow: hidden;

	&__header {
		display: flex;
		align-items: center;
		gap: var(--wf-space-sm);
		padding: var(--wf-space-sm) var(--wf-space-md);
		background: var(--el-fill-color-lighter);
	}

	&__time {
		font-size: 11px;
		color: var(--el-text-color-secondary);
		background: var(--el-fill-color);
		padding: 1px 6px;
		border-radius: 10px;
	}

	&__error {
		padding: var(--wf-space-sm) var(--wf-space-md);
		background: #fef0f0;
		color: var(--el-color-danger);
		font-size: 12px;
		line-height: 1.5;
		border-bottom: 1px solid var(--el-border-color-lighter);
	}

	&__section {
		padding: 10px 12px;
	}

	&__label {
		font-size: 12px;
		font-weight: 600;
		color: var(--el-text-color-regular);
		margin-bottom: 6px;
	}

	&__output {
		background: #f7f8fa;
		padding: var(--wf-space-sm);
		border-radius: 6px;
		font-family: monospace;
		white-space: pre-wrap;
		word-break: break-all;
		font-size: 11px;
		line-height: 1.4;
		max-height: 200px;
		overflow-y: auto;
		border: 1px solid var(--el-border-color-lighter);
		margin: 0;

		&::-webkit-scrollbar {
			width: 4px;
		}
		&::-webkit-scrollbar-thumb {
			background: #dcdfe6;
			border-radius: 2px;
		}
	}
}

:deep(.node-status-success .custom-flow-node) {
	border: 2px solid #67c23a !important;
	box-shadow: 0 0 10px rgba(103, 194, 58, 0.2) !important;
}
:deep(.node-status-error .custom-flow-node) {
	border: 2px solid #f56c6c !important;
	box-shadow: 0 0 10px rgba(245, 108, 108, 0.3) !important;
}
:deep(.node-status-running .custom-flow-node) {
	border: 2px solid #409eff !important;
	box-shadow: 0 0 12px rgba(64, 158, 255, 0.6) !important;
	animation: wf-node-pulse 1.5s infinite;
}

/* 
 * ⚠️ 极其重要的防坑警告 ⚠️
 * 绝对不要对 `:deep(.vue-flow__node)` 等外层容器应用包含 `transform` 的动画（如 scale/translate 等）。
 * Vue Flow 引擎在底层高度依赖内联的 `transform: translate(x, y)` 来固定所有节点的物理绝对坐标。
 * 如果在 CSS 中使用 `transform` 动画，会强制覆盖掉引擎的定位坐标，导致所有节点塌陷到 (0,0) 并互相重叠（节点漂移/消失）。
 *
 * 如需节点入场、选中或状态切换的动态效果（例如 scale 放缩），必须将动画加在自定义节点组件的最内层 wrapper 上。
 * （见 base-node.vue 中的 `.custom-flow-node-wrapper` 控制逻辑）
 */

/* 边交互增强 */
:deep(.vue-flow__edge) {
	.vue-flow__edge-interaction {
		stroke: transparent;
		stroke-width: 20px;
		cursor: pointer;
	}

	&:hover {
		.vue-flow__edge-path {
			stroke-width: 3px !important;
			filter: drop-shadow(0 0 4px currentColor);
		}
	}

	&.selected {
		.vue-flow__edge-path {
			stroke: var(--el-color-warning) !important;
			stroke-width: 3px !important;
			stroke-dasharray: 5;
			animation: wf-edge-dash-flow 0.6s linear infinite;
		}
	}
}

/* 多选框颜色调整 */
:deep(.vue-flow__selection) {
	background: rgba(64, 158, 255, 0.08);
	border: 1px solid var(--el-color-primary);
}
</style>
