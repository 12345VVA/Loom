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

				<!-- 右键上下文菜单（#23 键盘 a11y：方向键导航 + Enter 触发 + Escape 关闭） -->
				<div
					ref="contextMenuRef"
					v-if="contextMenu.visible"
					class="context-menu"
					role="menu"
					tabindex="-1"
					:style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
					@keydown="onMenuKeydown"
				>
					<div class="context-menu-item" role="menuitem" tabindex="-1" @click="editContextNode">
						<el-icon><edit /></el-icon>
						<span>{{ $t('配置节点') }}</span>
					</div>
					<div
						class="context-menu-item"
						role="menuitem"
						tabindex="-1"
						:aria-disabled="!canTestContextNode"
						@click="testContextNode"
						:class="{ 'is-disabled': !canTestContextNode }"
					>
						<el-icon><caret-right /></el-icon>
						<span>{{ $t('测试节点') }}</span>
					</div>
					<div class="context-menu-item" role="menuitem" tabindex="-1" @click="duplicateNode">
						<el-icon><copy-document /></el-icon>
						<span>{{ $t('复制节点') }}</span>
					</div>
					<div
						class="context-menu-item"
						role="menuitem"
						tabindex="-1"
						:aria-disabled="!canDistribute"
						@click="distributeHorizontal"
						:class="{ 'is-disabled': !canDistribute }"
					>
						<el-icon><grid /></el-icon>
						<span>{{ $t('水平等距分布') }}</span>
					</div>
					<div
						class="context-menu-item"
						role="menuitem"
						tabindex="-1"
						:aria-disabled="!canDistribute"
						@click="distributeVertical"
						:class="{ 'is-disabled': !canDistribute }"
					>
						<el-icon><operation /></el-icon>
						<span>{{ $t('垂直等距分布') }}</span>
					</div>
					<div class="context-menu-divider" role="separator" />
					<div
						class="context-menu-item context-menu-item--danger"
						role="menuitem"
						tabindex="-1"
						@click="deleteContextNode"
					>
						<el-icon><delete /></el-icon>
						<span>{{ $t('删除节点') }}</span>
					</div>
				</div>

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

import { ref, reactive, onMounted, onActivated, onDeactivated, onBeforeUnmount, computed, watch, provide, nextTick } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import { useCool } from '/@/cool';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';

// 导入 Vue Flow
import { VueFlow, useVueFlow } from '@vue-flow/core';
import type { Connection } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';
import '@vue-flow/minimap/dist/style.css';

// 导入 Element Plus 图标
import {
	VideoPlay,
	Cpu,
	Setting,
	Operation,
	UserFilled,
	CircleCheck,
	MagicStick,
	Refresh,
	Files,
	Picture,
	ArrowLeft,
	FolderChecked,
	Plus,
	Search,
	Edit,
	CopyDocument,
	ArrowDown,
	CaretRight,
	Delete,
	Download,
	Collection,
	Filter,
	Document,
	Brush,
	Grid
} from '@element-plus/icons-vue';

// Vue Flow 样式文件
import '@vue-flow/core/dist/style.css';
import '@vue-flow/core/dist/theme-default.css';
import '@vue-flow/controls/dist/style.css';

import {
	formatJson,
	genId,
	findInvalidNodeInput,
	isRequiredConfigMissing
} from '../utils';
import { getNodeMeta } from '../utils/node-type-registry';
import LogDrawer from '../components/log-drawer.vue';
import { UNTESTABLE_NODE_TYPES, OPEN_NODE_TEST_DIALOG_KEY } from '../components/constants';
import dayjs from 'dayjs';

import { useWorkflowTest } from '../composables/useWorkflowTest';
import { useAlignmentGuides } from '../composables/useAlignmentGuides';
import { useUndoRedo } from '../composables/useUndoRedo';
import { useNodeTest } from '../composables/useNodeTest';
import { useGraphBuilder } from '../composables/useGraphBuilder';
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

const { service } = useCool();
const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const { toObject, project, viewport, getSelectedNodes } = useVueFlow();

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

// 右键菜单状态
const contextMenu = reactive({
	visible: false,
	x: 0,
	y: 0,
	nodeId: ''
});

const contextMenuRef = ref<HTMLElement>();

// MiniMap 显隐（#28）：localStorage 持久化，默认显示
const miniMapVisible = ref(localStorage.getItem('loom_editor_minimap_visible') !== 'false');
function toggleMiniMap() {
	miniMapVisible.value = !miniMapVisible.value;
	localStorage.setItem('loom_editor_minimap_visible', String(miniMapVisible.value));
}

// 右键菜单键盘导航（#23 a11y）：方向键在可选项间循环、Enter/Space 触发、Escape 关闭
function onMenuKeydown(event: KeyboardEvent) {
	const root = contextMenuRef.value;
	if (!root) return;
	const items = Array.from(
		root.querySelectorAll<HTMLElement>('.context-menu-item:not(.is-disabled)')
	);
	if (items.length === 0) return;
	const currentIndex = items.findIndex(el => el === document.activeElement);
	if (event.key === 'ArrowDown') {
		event.preventDefault();
		items[(currentIndex + 1) % items.length]?.focus();
	} else if (event.key === 'ArrowUp') {
		event.preventDefault();
		items[(currentIndex - 1 + items.length) % items.length]?.focus();
	} else if (event.key === 'Enter' || event.key === ' ') {
		if (currentIndex >= 0) {
			event.preventDefault();
			items[currentIndex]?.click();
		}
	} else if (event.key === 'Escape') {
		contextMenu.visible = false;
	}
}

watch(
	() => contextMenu.visible,
	newVal => {
		if (!newVal) {
			contextMenu.nodeId = '';
		} else {
			// 打开时聚焦首个可选项，使方向键/Enter 可达（#23 a11y）
			nextTick(() => {
				contextMenuRef.value
					?.querySelector<HTMLElement>('.context-menu-item:not(.is-disabled)')
					?.focus();
			});
		}
	}
);

onBeforeUnmount(() => {
	stopLogPolling();
	window.removeEventListener('keydown', handleKeyDown);
});

interface WorkflowNodeData {
	config: Record<string, any>;
	runLog?: {
		status: 'success' | 'error' | 'running' | string;
		inputData?: any;
		outputData?: any;
		timeCost?: number;
	};
}

interface FlowNode {
	id: string;
	type: string;
	label: string;
	position: { x: number; y: number };
	data: WorkflowNodeData;
	style?: Record<string, any>;
	parentNode?: string;
}

interface FlowEdge {
	id: string;
	source: string;
	target: string;
	type?: string;
	animated?: boolean;
	style?: Record<string, any>;
	data?: {
		condition?: string;
		label?: string;
	};
	sourceHandle?: string;
}

// 可配置大模型配置列表
const aiProfiles = ref<Eps.profile[]>([]);

// 节点元素集合，包括 Nodes 和 Edges
const elements = ref<(FlowNode | FlowEdge)[]>([]);
const _upstreamCache = new Map<string, { result: any[]; version: number }>();
let _elementsVersion = 0;

let _persistSig = '';

const { canUndo, canRedo, pushSnapshot, undo, redo, init: initUndoRedo } = useUndoRedo(elements);

// 图构建（buildGraphPayload / persistSignature）抽离为 composable，便于单元测试
const { persistSignature, buildGraphPayload } = useGraphBuilder(elements);

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

// getUpstreamVariablesForNode moved here to fix hoisting issue
function getUpstreamVariablesForNode(nodeId: string) {
	const result: {
		nodeId: string;
		nodeLabel: string;
		variableName: string;
		nodeType: string;
		jsonFields?: any[];
		_isLoopContext?: boolean;
	}[] = [];
	const visited = new Set<string>();

	const targetNode = elements.value.find(el => !('source' in el) && el.id === nodeId) as
		| FlowNode
		| undefined;
	if (!targetNode) return result;

	function traceUpstream(currentId: string) {
		if (visited.has(currentId)) return;
		visited.add(currentId);
		const incomingEdges = elements.value.filter(
			(el: any) => 'source' in el && el.target === currentId
		) as FlowEdge[];
		for (const edge of incomingEdges) {
			const src = elements.value.find(
				(el: any) => !('source' in el) && el.id === edge.source
			) as FlowNode | undefined;
			if (!src) continue;
			if (src.type === 'start') {
				if (visited.has(src.id)) continue;
				visited.add(src.id);
				const inputVars: string[] = (src.data?.config as any)?.inputVariables || [];
				for (const varName of inputVars) {
					if (varName && varName.trim()) {
						result.push({
							nodeId: src.id,
							nodeLabel: src.label,
							variableName: varName.trim(),
							nodeType: src.type
						});
					}
				}
			} else {
				const cfg = src.data?.config || {};
				const outputVar = (cfg as any).outputVariable || '';
				if (outputVar) {
					const entry: any = {
						nodeId: src.id,
						nodeLabel: src.label,
						variableName: outputVar,
						nodeType: src.type
					};
					if (src.type === 'llm' && (cfg as any).outputFormat === 'json') {
						entry.jsonFields = (cfg as any).jsonFields || [];
					}
					result.push(entry);
				}
				traceUpstream(src.id);
			}
		}
	}
	traceUpstream(nodeId);

	// 循环上下文变量注入
	const parentId = (targetNode as any).parentNode;
	if (parentId) {
		const groupNode = elements.value.find(el => !('source' in el) && el.id === parentId) as
			| FlowNode
			| undefined;
		if (groupNode?.type === 'loop_body_group') {
			const ctrlId = groupNode.data?.config?.controllerNodeId;
			if (ctrlId) {
				const ctrlNode = elements.value.find(
					el => !('source' in el) && el.id === ctrlId
				) as FlowNode | undefined;
				if (ctrlNode) {
					const itemVar = ctrlNode.data?.config?.itemVariable || 'loop_item';
					result.unshift({
						nodeId: ctrlNode.id,
						nodeLabel: ctrlNode.label,
						variableName: itemVar,
						nodeType: ctrlNode.type,
						_isLoopContext: true
					});
				}
			}
		}
	}

	return result;
}

// 单节点测试 composable
const { nodeTestDialog, openNodeTestDialog, startNodeTest, closeNodeTestDialog, clearMockCache } = useNodeTest(
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

const hasIncompleteNodes = computed(() => {
	return elements.value.some((el: any) => !('source' in el) && isRequiredConfigMissing(el));
});

// 收集当前节点的上游可达变量
const upstreamVariables = computed(() => {
	if (!selectedNode.value) return [];
	const nodeId = selectedNode.value.id;
	const cached = _upstreamCache.get(nodeId);
	if (cached && cached.version === _elementsVersion) {
		return cached.result;
	}
	const result = getUpstreamVariablesForNode(nodeId);
	_upstreamCache.set(nodeId, { result, version: _elementsVersion });
	return result;
});

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
		contextMenu.visible = false;
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

function deleteSelectedElements() {
	const nodesToRemove = elements.value.filter(el => !('source' in el) && (el as any).selected);
	const edgesToRemove = elements.value.filter(el => 'source' in el && (el as any).selected);

	if (nodesToRemove.length > 0 || edgesToRemove.length > 0) {
		// 级联清理关联 group + 子节点坐标转换（planNodeRemoval）
		elements.value = planNodeRemoval(elements.value, {
			nodeIds: nodesToRemove.map(n => n.id),
			edgeIds: edgesToRemove.map(e => e.id)
		});
		clearMockCache(nodesToRemove.map(n => n.id));

		if (selectedNodeId.value && nodesToRemove.some(n => n.id === selectedNodeId.value)) {
			selectedNodeId.value = null;
		}

		ElMessage.success(t('已删除所选元素'));
		pushSnapshot();
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
		_elementsVersion++;
		_upstreamCache.clear();
		if (loaded.value) {
			isDirty.value = true;
		}
	},
	{ deep: true, flush: 'post' }
);

async function fetchWorkflowData() {
	try {
		const res = await (service as any).workflow.definition.info({ id: workflowId.value });
		workflowName.value = res.name;
		workflowCode.value = res.code;
		workflowDescription.value = res.description || '';

		// 加载草稿拓扑（纯版本表模型：graph 存版本表，info 回填 draftGraphJson）
		if (res.draftGraphJson && res.draftGraphJson !== '{}') {
			const graph = JSON.parse(res.draftGraphJson);

			// 转换 JSON 到 Vue Flow 的 elements
			const loadedElements = graph.elements || [];
			// 转换 tool_executor 的 arguments
			loadedElements.forEach((el: any) => {
				if (el.type === 'tool_executor' && el.data?.config) {
					if (el.data.config.arguments && !el.data.config.argumentsJson) {
						el.data.config.argumentsJson = JSON.stringify(
							el.data.config.arguments,
							null,
							2
						);
					}
				}
				// 兼容旧数据
				if (el.type === 'start' && el.data?.config && !el.data.config.inputVariables) {
					el.data.config.inputVariables = ['query'];
				}
				if (el.type === 'end' && el.data?.config) {
					if (!el.data.config.outputFormat) {
						el.data.config.outputFormat = el.data.config.outputTemplate
							? 'text'
							: 'json';
					}
					if (!el.data.config.outputFields) {
						el.data.config.outputFields = [];
					}
				}
				if (el.type === 'llm' && el.data?.config && !el.data.config.jsonFields) {
					el.data.config.jsonFields = [];
				}
				// 稳定 handle 迁移：为 switch/intent 分支补稳定 id（缺失时生成）
				if (el.type === 'switch' && el.data?.config?.cases) {
					el.data.config.cases.forEach((c: any) => {
						if (!c.id) c.id = genId();
					});
				}
				if (el.type === 'intent_classifier' && el.data?.config?.intents) {
					el.data.config.intents.forEach((i: any) => {
						if (!i.id) i.id = genId();
					});
				}
			});

			// 旧工作流兼容：从 condition/switch/intent_classifier 节点的 config 反向重建边的 sourceHandle
			const nodesMap = new Map<string, any>();
			for (const el of loadedElements) {
				if (!('source' in el)) nodesMap.set(el.id, el);
			}
			// 稳定 handle 迁移：把旧下标格式（case_N / intent_N）升级为稳定 id 格式。
			// 仅纯数字下标才迁移，已是 case_<id> 的不动，保证幂等。
			for (const el of loadedElements) {
				if (!('source' in el) || !el.sourceHandle) continue;
				const srcNode = nodesMap.get(el.source);
				if (!srcNode) continue;
				if (/^case_\d+$/.test(el.sourceHandle) && srcNode.type === 'switch') {
					const idx = parseInt(el.sourceHandle.split('_')[1]);
					const c = srcNode.data?.config?.cases?.[idx];
					if (c?.id) el.sourceHandle = 'case_' + c.id;
				} else if (/^intent_\d+$/.test(el.sourceHandle) && srcNode.type === 'intent_classifier') {
					const idx = parseInt(el.sourceHandle.split('_')[1]);
					const it = srcNode.data?.config?.intents?.[idx];
					if (it?.id) el.sourceHandle = 'intent_' + it.id;
				}
			}
			for (const el of loadedElements) {
				if (!('source' in el) || el.sourceHandle) continue;
				const srcNode = nodesMap.get(el.source);
				if (!srcNode) continue;
				if (srcNode.type === 'condition') {
					const cfg = srcNode.data?.config || {};
					if (el.target === cfg.trueRoute) el.sourceHandle = 'true';
					else if (el.target === cfg.falseRoute) el.sourceHandle = 'false';
				} else if (srcNode.type === 'switch') {
					const cfg = srcNode.data?.config || {};
					const cases = cfg.cases || [];
					if (el.target === cfg.defaultRoute) el.sourceHandle = 'default';
					else {
						for (let i = 0; i < cases.length; i++) {
							if (el.target === cases[i].targetRoute) {
								el.sourceHandle = 'case_' + (cases[i].id ?? i);
								break;
							}
						}
					}
				} else if (srcNode.type === 'intent_classifier') {
					const cfg = srcNode.data?.config || {};
					const intents = cfg.intents || [];
					if (el.target === cfg.defaultRoute) {
						el.sourceHandle = 'default';
					} else {
						for (let i = 0; i < intents.length; i++) {
							if (el.target === intents[i].targetRoute) {
								el.sourceHandle = 'intent_' + (intents[i].id ?? i);
								break;
							}
						}
					}
				}
			}

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

// 提取的公共添加节点逻辑
function handleAddNode(type: string, x: number, y: number) {
	// 开始/结束节点全局唯一，已存在时阻止添加
	if (type === 'start' || type === 'end') {
		const exists = elements.value.some(el => !('source' in el) && el.type === type);
		if (exists) {
			ElMessage.warning(
				t(
					type === 'start'
						? '开始节点已存在，画布中仅允许一个'
						: '结束节点已存在，画布中仅允许一个'
				)
			);
			return;
		}
	}

	const id = `node_${type}_${Date.now()}`;
	const label = getNextLabel(type);

	// 初始化节点特定 config
	let config: Record<string, any> = {};
	if (type === 'llm') {
		config = {
			modelProfileCode: '',
			systemPromptTemplate: '',
			promptTemplate: '',
			outputFormat: 'text',
			jsonFields: [],
			outputVariable: getUniqueOutputVar(label, 'output')
		};
	} else if (type === 'condition') {
		config = { expression: '', trueRoute: '', falseRoute: '' };
	} else if (type === 'switch') {
		config = { variable: '', cases: [], defaultRoute: '' };
	} else if (type === 'human_input') {
		config = { message: '', outputVariable: getUniqueOutputVar(label, 'approval_status') };
	} else if (type === 'intent_classifier') {
		config = { modelProfileCode: '', intents: [], defaultRoute: '' };
	} else if (type === 'loop_controller') {
		config = {
			listVariable: 'list_variable',
			itemVariable: 'loop_item',
			outputVariable: getUniqueOutputVar(label, 'loop_results'),
			loopBodyRoute: '',
			exitRoute: ''
		};
	} else if (type === 'batch_processor') {
		config = {
			batchListVariable: 'batch_list_variable',
			itemVariable: 'batch_item',
			concurrencyLimit: 5,
			outputVariable: getUniqueOutputVar(label, 'batch_results'),
			loopBodyRoute: '',
			exitRoute: ''
		};
	} else if (type === 'image_generator') {
		config = {
			modelProfileCode: '',
			promptTemplate: '',
			size: '',
			imageVariable: '',
			imageTemplate: '',
			optionsJson: '{}',
			outputVariable: getUniqueOutputVar(label, 'image_url')
		};
	} else if (type === 'tool_executor') {
		config = {
			toolCode: '',
			argumentsJson: '{}',
			outputVariable: getUniqueOutputVar(label, 'tool_result')
		};
	} else if (type === 'variable_assignment') {
		config = { assignments: [] };
	} else if (type === 'variable_transform') {
		config = {
			input_variable: '',
			transform_type: 'join_array',
			transform_args: {},
			output_variable: getUniqueOutputVar(label, 'transformed_value')
		};
	} else if (type === 'end') {
		config = { outputFormat: 'json', outputFields: [] };
	}

	const newNode: any = {
		id,
		type,
		label,
		position: { x, y },
		data: { config }
	};

	// 检查是否落入 group 中
	const groups = elements.value.filter(
		(el: any) => !('source' in el) && el.type === 'loop_body_group'
	) as FlowNode[];

	let targetGroupId: string | undefined;
	for (const g of groups) {
		const gW = parseFloat((g as any).style?.width || '400');
		const gH = parseFloat((g as any).style?.height || '250');
		const pos = g.position;
		if (x + 50 >= pos.x && x + 50 <= pos.x + gW && y + 20 >= pos.y && y + 20 <= pos.y + gH) {
			targetGroupId = g.id;
			// 坐标相对于 parent
			const innerX = x - pos.x;
			let innerY = y - pos.y;

			// 防止掉落时节点下边缘和上边缘溢出（节点默认高约 56px）
			if (innerY + 60 > gH) {
				innerY = gH - 70;
			}
			if (innerY < 40) {
				innerY = 40; // 避开 group-header
			}

			newNode.position.x = innerX;
			newNode.position.y = innerY;
			newNode.parentNode = targetGroupId;
			newNode.expandParent = true;
			break;
		}
	}

	elements.value.push(newNode);

	// 自动创建组容器（不连线，由用户自行从容器 handle 连出）
	if (type === 'loop_controller' || type === 'batch_processor') {
		const groupId = `node_loop_body_group_${Date.now()}`;
		const groupNode = {
			id: groupId,
			type: 'loop_body_group',
			label: type === 'loop_controller' ? `${label} - 循环体` : `${label} - 批处理体`,
			position: { x: x + 250, y: y - 50 },
			style: { width: '400px', height: '250px' },
			data: { config: { controllerNodeId: id } }
		};
		elements.value.push(groupNode);
	}

	// [P0 修复] 快照在 group 加入后拍摄，保证 undo 时主节点 + group 原子撤销
	// （原快照在加 group 前拍摄，undo 后 group 残留）
	pushSnapshot();
}

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

function getTypeName(type: string) {
	const meta = getNodeMeta(type);
	return t(meta.labelKey || '未知节点');
}

function getNextLabel(type: string): string {
	const baseName = getTypeName(type);
	const sameTypeNodes = elements.value.filter(
		(el: any) => !('source' in el) && el.type === type
	) as FlowNode[];
	if (sameTypeNodes.length === 0) return baseName;

	let maxNum = 0;
	for (const n of sameTypeNodes) {
		if (n.label === baseName) {
			maxNum = Math.max(maxNum, 1);
		} else {
			const match = n.label.match(new RegExp(`${baseName} (\\d+)$`));
			if (match) {
				maxNum = Math.max(maxNum, parseInt(match[1]));
			}
		}
	}
	return `${baseName} ${maxNum + 1}`;
}

function sanitizeLabel(label: string): string {
	return label.replace(/\s+/g, '').replace(/[^a-zA-Z0-9_一-鿿]/g, '');
}

function getUniqueOutputVar(label: string, defaultVar: string): string {
	const prefix = sanitizeLabel(label);
	const candidate = `${prefix}_${defaultVar}`;
	const existingVars = new Set<string>();
	for (const el of elements.value) {
		if ('source' in el) continue;
		const outVar = (el as FlowNode).data?.config?.outputVariable;
		if (outVar) existingVars.add(outVar);
	}
	if (!existingVars.has(candidate)) return candidate;
	let i = 2;
	while (existingVars.has(`${candidate}_${i}`)) i++;
	return `${candidate}_${i}`;
}

// 画布内连线
function onConnect(params: Connection) {
	const source = params.source || '';
	const target = params.target || '';
	const sourceHandle = params.sourceHandle;

	// 查找源节点
	const srcNode = elements.value.find((el: any) => !('source' in el) && el.id === source) as
		| FlowNode
		| undefined;
	if (!srcNode) return;

	// 连线验证
	if (source === target) {
		ElMessage.warning(t('不能连接自身'));
		return;
	}
	if (srcNode.type === 'end') {
		ElMessage.warning(t('结束节点不能有出边'));
		return;
	}

	const tgtNode = elements.value.find((el: any) => !('source' in el) && el.id === target) as
		| FlowNode
		| undefined;
	if (tgtNode?.type === 'start') {
		ElMessage.warning(t('开始节点不能有入边'));
		return;
	}

	// condition 每个 Handle 只能连一个目标
	if (srcNode.type === 'condition' && sourceHandle) {
		const existing = elements.value.some(
			(el: any) =>
				'source' in el && el.source === source && (el as any).sourceHandle === sourceHandle
		);
		if (existing) {
			ElMessage.warning(t(sourceHandle === 'true' ? 'True 分支已连线' : 'False 分支已连线'));
			return;
		}
	}

	// intent_classifier / switch 每个 Handle 只能连一个目标
	if ((srcNode.type === 'intent_classifier' || srcNode.type === 'switch') && sourceHandle) {
		const existing = elements.value.some(
			(el: any) =>
				'source' in el && el.source === source && (el as any).sourceHandle === sourceHandle
		);
		if (existing) {
			ElMessage.warning(t('该端口已连线'));
			return;
		}
	}

	// 禁止跨组连线（外部节点不能直连内部节点，内部节点也不能直连外部节点）
	if ((srcNode as any).parentNode !== (tgtNode as any).parentNode) {
		ElMessage.warning(t('禁止跨容器连线，内部节点与外部节点须相互独立'));
		return;
	}

	// 去重：同 source + target + sourceHandle 视为重复。
	// [P0 修复] 加入 sourceHandle 比较，避免 condition/switch 多分支连同一目标被误拒
	const exists = elements.value.some(
		(el: any) =>
			'source' in el &&
			el.source === source &&
			el.target === target &&
			(el as any).sourceHandle === sourceHandle
	);
	if (exists) return;

	// 写回 config 路由（兼容旧逻辑）
	if (srcNode.type === 'condition') {
		const cfg = srcNode.data?.config;
		if (cfg) {
			if (sourceHandle === 'true') cfg.trueRoute = target;
			if (sourceHandle === 'false') cfg.falseRoute = target;
		}
	}

	// 推导边标签
	const label = getEdgeLabel(source, sourceHandle ?? undefined, srcNode);
	const isConditional =
		srcNode.type === 'condition' ||
		srcNode.type === 'switch' ||
		srcNode.type === 'intent_classifier';

	const newEdge: any = {
		id: 'edge_' + source + '_' + target,
		source,
		target,
		sourceHandle,
		animated: !isConditional,
		type: label ? 'label' : 'default',
		data: { label },
		style: { strokeWidth: 2 }
	};
	elements.value.push(newEdge);
	pushSnapshot();
}

function getEdgeLabel(
	source: string,
	sourceHandle?: string,
	srcNode?: FlowNode
): string | undefined {
	if (!srcNode) return undefined;
	if (srcNode.type === 'condition') {
		if (sourceHandle === 'true') return 'True';
		if (sourceHandle === 'false') return 'False';
	}
	if (srcNode.type === 'switch') {
		if (sourceHandle === 'default') return '默认';
		if (sourceHandle?.startsWith('case_')) {
			const rest = sourceHandle.slice(5);
			const byId = srcNode.data?.config?.cases?.find((c: any) => c.id === rest);
			if (byId) return byId.value || 'Case';
			if (/^\d+$/.test(rest)) {
				const idx = parseInt(rest);
				return srcNode.data?.config?.cases?.[idx]?.value || 'Case ' + (idx + 1);
			}
			return 'Case';
		}
	}
	if (srcNode.type === 'intent_classifier') {
		if (sourceHandle === 'default') return '默认';
		if (sourceHandle?.startsWith('intent_')) {
			const rest = sourceHandle.slice(7);
			const byId = srcNode.data?.config?.intents?.find((i: any) => i.id === rest);
			if (byId) return byId.name || 'Intent';
			if (/^\d+$/.test(rest)) {
				const idx = parseInt(rest);
				return srcNode.data?.config?.intents?.[idx]?.name || 'Intent ' + (idx + 1);
			}
			return 'Intent';
		}
	}
	return undefined;
}

function onPaneReady(instance: any) {
	instance.fitView();
}

function onNodeClick(event: { node: any }) {
	selectedNodeId.value = event.node.id;
	contextMenu.visible = false;
}

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

	const groups = elements.value.filter(
		(el: any) => !('source' in el) && el.type === 'loop_body_group'
	) as FlowNode[];
	for (const g of groups) {
		const gW = parseFloat((g as any).style?.width || '400');
		const gH = parseFloat((g as any).style?.height || '250');
		const pos = g.position;
		if (flowX >= pos.x && flowX <= pos.x + gW && flowY >= pos.y && flowY <= pos.y + gH) {
			const domNode = document.querySelector(`[data-id="${g.id}"] .loop-body-group-node`);
			if (domNode) domNode.classList.add('is-drag-over');
			break;
		}
	}
}

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

function onNodeDragStop() {
	clearGuides();
	pushSnapshot();
}

// 右键上下文菜单边界检测
function clampMenuPosition(x: number, y: number) {
	const menuW = 180;
	const menuH = 180;
	const vw = window.innerWidth;
	const vh = window.innerHeight;
	return {
		x: x + menuW > vw ? x - menuW : x,
		y: y + menuH > vh ? y - menuH : y
	};
}

// 右键上下文菜单
function onNodeContextMenu(event: any) {
	event.event?.preventDefault();
	const node = event.node;
	if (!node) return;
	const rawX = event.event?.clientX || 0;
	const rawY = event.event?.clientY || 0;
	const pos = clampMenuPosition(rawX, rawY);
	contextMenu.visible = true;
	contextMenu.x = pos.x;
	contextMenu.y = pos.y;
	contextMenu.nodeId = node.id;
}

function onPaneContextMenu(event: any) {
	(event?.event ?? event)?.preventDefault?.();
	contextMenu.visible = false;
}

function onEdgeContextMenu(event: any) {
	(event?.event ?? event)?.preventDefault?.();
	contextMenu.visible = false;
}

function editContextNode() {
	selectedNodeId.value = contextMenu.nodeId;
	contextMenu.visible = false;
}

const canTestContextNode = computed(() => {
	if (!contextMenu.nodeId) return false;
	const node = elements.value.find(el => !('source' in el) && el.id === contextMenu.nodeId) as
		| FlowNode
		| undefined;
	if (!node) return false;
	return !UNTESTABLE_NODE_TYPES.includes(node.type);
});

const canDistribute = computed(() => {
	const selectedNodes = getSelectedNodes.value;
	return selectedNodes.length >= 3;
});

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
	contextMenu.visible = false;
}

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
	contextMenu.visible = false;
}

// Provide node test dialog opener to sub-components (like base-node, node-config-panel)
provide(OPEN_NODE_TEST_DIALOG_KEY, openNodeTestDialog);

// 单节点测试：右键菜单适配层（状态管理已迁移至 useNodeTest composable）
async function testContextNode() {
	if (!canTestContextNode.value) {
		ElMessage.warning(t('该类型节点不支持单独测试'));
		return;
	}
	contextMenu.visible = false;
	await openNodeTestDialog(contextMenu.nodeId);
}

function duplicateNode() {
	const srcNode = elements.value.find(
		(el: any) => !('source' in el) && el.id === contextMenu.nodeId
	) as FlowNode | undefined;
	if (!srcNode) return;

	if (srcNode.type === 'start' || srcNode.type === 'end') {
		ElMessage.warning(
			t(
				srcNode.type === 'start'
					? '开始节点已存在，画布中仅允许一个'
					: '结束节点已存在，画布中仅允许一个'
			)
		);
		contextMenu.visible = false;
		return;
	}

	const newId = `node_${srcNode.type}_${Date.now()}`;
	const newLabel = getNextLabel(srcNode.type);
	const srcCopy = JSON.parse(JSON.stringify(srcNode));
	delete srcCopy.class;
	if (srcCopy.data) {
		delete srcCopy.data.runLog;
		delete srcCopy.data.runData;
		// 复制节点的 case/intent 重新分配稳定 id，避免与源节点端口 id 重复
		if (srcCopy.data.config?.cases) {
			srcCopy.data.config.cases.forEach((c: any) => {
				c.id = genId();
			});
		}
		if (srcCopy.data.config?.intents) {
			srcCopy.data.config.intents.forEach((i: any) => {
				i.id = genId();
			});
		}
	}
	
	// 基准坐标：源节点位于 group 内时其 position 是相对父节点的局部坐标，
	// 复制后放主画布需累加 group 绝对偏移，否则副本会漂移到错误位置
	let baseX = srcNode.position.x;
	let baseY = srcNode.position.y;
	if (srcNode.parentNode) {
		const group = elements.value.find((el: any) => el.id === srcNode.parentNode) as any;
		if (group?.position) {
			baseX += group.position.x;
			baseY += group.position.y;
		}
	}
	let newX = baseX + 40;
	let newY = baseY + 40;
	while (elements.value.some((el: any) => el.position && el.position.x === newX && el.position.y === newY)) {
		newX += 40;
		newY += 40;
	}

	const newNode: any = {
		...srcCopy,
		id: newId,
		label: newLabel,
		position: { x: newX, y: newY }
	};

	// 处理变量名去重
	if (newNode.data?.config?.outputVariable) {
		const baseVarName = newNode.data.config.outputVariable.replace(/_\d+$/, '');
		newNode.data.config.outputVariable = getUniqueOutputVar(newLabel, baseVarName);
	}

	// 复制出的节点不保留 parentNode（放在主画布）
	delete newNode.parentNode;
	delete newNode.extent;
	delete newNode.expandParent;
	elements.value.push(newNode);
	contextMenu.visible = false;
	pushSnapshot();
	ElMessage.success(t('已复制节点'));
}

function deleteContextNode() {
	const nodeId = contextMenu.nodeId;
	// 级联清理关联 group + 子节点坐标转换（planNodeRemoval）
	elements.value = planNodeRemoval(elements.value, { nodeIds: [nodeId] });
	clearMockCache([nodeId]);
	if (selectedNodeId.value === nodeId) {
		selectedNodeId.value = null;
	}
	contextMenu.visible = false;
	ElMessage.success(t('已删除节点'));
	pushSnapshot();
}

function deleteSelectedNode() {
	if (!selectedNodeId.value) return;
	const nodeId = selectedNodeId.value;
	// 级联清理关联 group + 子节点坐标转换（planNodeRemoval）
	elements.value = planNodeRemoval(elements.value, { nodeIds: [nodeId] });
	clearMockCache([nodeId]);
	selectedNodeId.value = null;
}

// buildGraphPayload / persistSignature 已抽离至 useGraphBuilder composable

// 将 Vue Flow 画布信息转换打包为后端标准工作流 JSON 格式并存储
async function saveWorkflow() {
	if (!workflowId.value) return;
	// [P0 修复] 并发互斥：快速双击保存时阻止重入，避免竞态写入
	if (saving.value) return;
	// 阻断：节点 inputs 变量名非法（空/格式错/重名）时不允许保存
	const invalidInput = findInvalidNodeInput(elements.value);
	if (invalidInput) {
		ElMessage.warning(invalidInput.error);
		return;
	}
	saving.value = true;
	try {
		// 1. 拆分连线与节点 (TS-safe 属性检查)
		const nodes = elements.value.filter(el => !('source' in el)) as FlowNode[];
		const edges = elements.value.filter(el => 'source' in el) as FlowEdge[];

		// 2. 检查图结构完整性并给以提示
		const warnings: string[] = [];
		const startNodes = nodes.filter(n => n.type === 'start');
		if (startNodes.length === 0) {
			warnings.push(t('工作流缺失"开始节点"，请在画布中添加唯一入口！'));
		} else if (startNodes.length > 1) {
			warnings.push(t('工作流存在多个"开始节点"，请在画布中保留唯一入口！'));
		}

		// 检查循环/批处理容器内部是否合法（多个起点或死循环）
		const groups = nodes.filter(n => n.type === 'loop_body_group');
		for (const g of groups) {
			const bodyNodeIds = nodes.filter(n => (n as any).parentNode === g.id).map(n => n.id);
			if (bodyNodeIds.length > 0) {
				const entries = bodyNodeIds.filter(
					nid => !edges.some(e => e.target === nid && bodyNodeIds.includes(e.source))
				);
				if (entries.length > 1) {
					const names = entries
						.map(eid => nodes.find(n => n.id === eid)?.label || eid)
						.join(', ');
					warnings.push(
						t('容器 "') +
							(g.label || g.id) +
							t('" 内存在多个没有输入的起点节点: ') +
							names +
							t('。请用内部连线明确它们的执行顺序！')
					);
				} else if (entries.length === 0) {
					warnings.push(
						t('容器 "') +
							(g.label || g.id) +
							t('" 内部形成了死循环闭环，无法确定起始节点！')
					);
				}
			}
		}

		// 检查 Switch 分支节点是否配置完整
		const switchNodes = nodes.filter(n => n.type === 'switch');
		for (const n of switchNodes) {
			const conf = n.data?.config || {};
			if (!conf.variable || !conf.variable.trim()) {
				warnings.push(t('节点"') + (n.label || n.id) + t('"未指定匹配变量名！'));
			}
			const cases = conf.cases || [];
			const seenCaseVals = new Set<string>();
			for (const c of cases) {
				if (!c.value || !c.value.trim()) {
					warnings.push(t('节点"') + (n.label || n.id) + t('"存在空白的 Case 匹配值！'));
				}
				if (c.value) {
					if (seenCaseVals.has(c.value.trim())) {
						warnings.push(
							t('节点"') +
								(n.label || n.id) +
								t('"中存在重复的 Case 匹配值：') +
								c.value.trim()
						);
					}
					seenCaseVals.add(c.value.trim());
				}
			}
		}

		// 检查结束节点是否配置完整
		const endNode = nodes.find(n => n.type === 'end');
		if (endNode) {
			const conf = endNode.data?.config || {};
			if (conf.outputFormat === 'json') {
				const fields = conf.outputFields || [];
				const seenFieldNames = new Set<string>();
				for (const f of fields) {
					if (!f.name || !f.name.trim()) {
						warnings.push(t('结束节点中存在未命名的输出字段！'));
					}
					if (f.name) {
						if (seenFieldNames.has(f.name.trim())) {
							warnings.push(t('结束节点中存在重复的输出字段名：') + f.name.trim());
						}
						seenFieldNames.add(f.name.trim());
					}
				}
			} else {
				if (!conf.outputTemplate || !conf.outputTemplate.trim()) {
					warnings.push(t('结束节点未配置输出结构模板！'));
				}
			}
		}

		// 检查孤立节点
		const connectedNodeIds = new Set<string>();
		edges.forEach(e => {
			if (e.source) connectedNodeIds.add(e.source);
			if (e.target) connectedNodeIds.add(e.target);
		});
		const isolatedNodes = nodes.filter(
			n =>
				n.type !== 'start' &&
				n.type !== 'end' &&
				!n.parentNode &&
				!connectedNodeIds.has(n.id)
		);
		if (isolatedNodes.length > 0) {
			warnings.push(
				t('发现孤立的工作节点：') +
					isolatedNodes.map(n => n.label || n.id).join(', ') +
					t('，请建立输入和输出连线！')
			);
		}

		// 检查模型节点是否已选择 Profile
		const modelRequiredTypes = ['llm', 'intent_classifier', 'image_generator'];
		const missingProfileNodes = nodes.filter(
			n =>
				modelRequiredTypes.includes(n.type) &&
				!(n.data?.config as any)?.modelProfileCode?.trim()
		);
		if (missingProfileNodes.length > 0) {
			warnings.push(
				t('以下节点未选择模型 Profile：') +
					missingProfileNodes.map(n => n.label || n.id).join(', ') +
					t('，请先在配置面板中选择模型！')
			);
		}

		// 检查是否存在重复的输出变量名（排除互斥条件分支）
		// 构建条件节点的互斥分组：同一条件节点不同分支上的节点互斥，不会同时执行
		const exclusiveGroups: Map<string, Set<string>> = new Map();
		const conditionalTypes = ['condition', 'intent_classifier', 'switch'];
		for (const n of nodes) {
			if (conditionalTypes.includes(n.type)) {
				const downstreamIds = edges.filter(e => e.source === n.id).map(e => e.target);
				if (downstreamIds.length > 1) {
					const group = new Set(downstreamIds);
					for (const id of downstreamIds) {
						exclusiveGroups.set(id, group);
					}
				}
			}
		}
		const varNameToNodes = new Map<string, string[]>();
		for (const n of nodes) {
			const outVar = (n.data?.config as any)?.outputVariable?.trim();
			if (outVar) {
				const list = varNameToNodes.get(outVar) || [];
				// 检查已有的同名节点是否与当前节点互斥
				const isExclusive = list.every(existingLabel => {
					const existingNode = nodes.find(nn => (nn.label || nn.id) === existingLabel);
					if (!existingNode) return false;
					const groupA = exclusiveGroups.get(n.id);
					const groupB = exclusiveGroups.get(existingNode.id);
					return groupA && groupB && groupA === groupB;
				});
				if (isExclusive) continue;
				list.push(n.label || n.id);
				varNameToNodes.set(outVar, list);
			}
		}
		const duplicates = [...varNameToNodes.entries()].filter(([, ns]) => ns.length > 1);
		if (duplicates.length > 0) {
			const detail = duplicates
				.map(([varName, nodeNames]) => `${varName} (${nodeNames.join(', ')})`)
				.join('; ');
			warnings.push(t('输出变量名重复，后执行节点会覆盖先前结果：') + detail);
		}

		// 如果存在校验警告，拦截保存并弹窗提醒
		if (warnings.length > 0) {
			ElMessageBox.alert(
				warnings.map((w, idx) => `${idx + 1}. ${w}`).join('<br>'),
				t('保存失败 (检测到拓扑问题)'),
				{
					confirmButtonText: t('确定'),
					type: 'error',
					dangerouslyUseHTMLString: true
				}
			);
			saving.value = false;
			return;
		}

		// 3. 验证并构造后端标准解析结构
		const graphPayload = buildGraphPayload();

		// 4. 保存草稿（纯版本表模型：graph 存版本表草稿，未发布不上线）
		await (service as any).workflow.definition.saveDraft({
			definitionId: Number(workflowId.value),
			code: workflowCode.value,
			name: workflowName.value,
			description: workflowDescription.value,
			graphJson: JSON.stringify(graphPayload)
		});

		ElMessage.success(t('草稿保存成功（发布后生效）'));
		isDirty.value = false;
		// 保存成功：以当前拓扑签名重置 isDirty 比较基线
		_persistSig = persistSignature(elements.value);
		return true;
	} catch (err: any) {
		ElMessage.error(t('保存失败: ') + (err.message || err));
		return false;
	} finally {
		saving.value = false;
	}
}

// 发布草稿：先保存最新草稿，再 publish（一步上线；运行中实例按其版本继续跑、不受影响）
async function publishWorkflow() {
	if (!workflowId.value) return;
	try {
		await ElMessageBox.confirm(
			t('发布后新启动的实例将使用此版本，正在运行的实例按其版本继续跑、不受影响。是否先保存并发布？'),
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
	gap: 8px;
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
		gap: 8px;
		padding: 8px 12px;
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
		padding: 8px 12px;
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
		padding: 8px;
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

.context-menu {
	position: fixed;
	z-index: 1000;
	background: #fff;
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
	padding: 4px 0;
	min-width: 160px;

	.context-menu-item {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 16px;
		font-size: 13px;
		cursor: pointer;
		transition: background 0.15s;

		&:hover {
			background: var(--el-fill-color-light);
		}

		.el-icon {
			font-size: 14px;
		}

		&--danger {
			color: var(--el-color-danger);
		}
	}

	.context-menu-divider {
		height: 1px;
		background: var(--el-border-color-lighter);
		margin: 4px 0;
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
