<template>
	<div class="workflow-editor-container">
		<!-- 头部工具栏 -->
		<div class="editor-header">
			<div class="editor-header__left">
				<el-button :icon="ArrowLeft" circle @click="goBack" />
				<span class="workflow-title">{{ workflowName || $t('未命名工作流') }}</span>
				<el-tag size="small" type="info" class="workflow-code">{{ workflowCode }}</el-tag>
			</div>
			<div class="editor-header__right">
				<el-button type="primary" :icon="FolderChecked" :loading="saving" @click="saveWorkflow">
					{{ $t('保存工作流') }}
				</el-button>
			</div>
		</div>

		<!-- 主画布区 -->
		<div class="editor-body">
			<!-- 左侧节点库 -->
			<div class="node-sidebar">
				<div class="sidebar-title">{{ $t('节点库') }}</div>
				<div class="sidebar-description">{{ $t('拖拽节点到画布中进行设计') }}</div>

				<div class="node-templates">
					<div
						v-for="item in nodeTemplates"
						:key="item.type"
						class="node-template-item"
						:class="'node-template-item--' + item.type"
						draggable="true"
						@dragstart="onDragStart($event, item.type)"
					>
						<el-icon class="template-icon">
							<component :is="item.icon" />
						</el-icon>
						<div class="template-info">
							<div class="template-name">{{ item.name }}</div>
							<div class="template-desc">{{ item.desc }}</div>
						</div>
					</div>
				</div>
			</div>

			<!-- 画布中央 -->
			<div class="canvas-wrapper" @drop="onDrop" @dragover.prevent>
				<vue-flow
					v-model="elements"
					:node-types="nodeTypes"
					:default-edge-options="defaultEdgeOptions"
					@connect="onConnect"
					@pane-ready="onPaneReady"
					@node-click="onNodeClick"
					@pane-click="onPaneClick"
				>
					<background pattern-color="#e0e0e0" :gap="16" />
					<controls position="bottom-right" />
				</vue-flow>
			</div>

			<!-- 右侧节点配置面板 -->
			<node-config-panel
				v-if="selectedNode"
				:selected-node="selectedNode"
				:upstream-variables="upstreamVariables"
				:variable-syntax-hints="variableSyntaxHints"
				:available-target-nodes="availableTargetNodes"
				:ai-profiles="aiProfiles"
				@delete="deleteSelectedNode"
			/>
			<div v-else class="config-panel-empty">
				<el-empty :description="$t('在画布中点击节点以进行属性配置')" />
			</div>
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'workflow-editor'
});

import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useCool } from '/@/cool';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';

// 导入 Vue Flow
import { VueFlow, useVueFlow } from '@vue-flow/core';
import type { Connection } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';

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
	Plus
} from '@element-plus/icons-vue';

// Vue Flow 样式文件
import '@vue-flow/core/dist/style.css';
import '@vue-flow/core/dist/theme-default.css';
import '@vue-flow/controls/dist/style.css';

// 导入重构的子组件
import NodeConfigPanel from '../components/node-config-panel.vue';
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

const { service } = useCool();
const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const { toObject } = useVueFlow();

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
	tool_executor: ToolExecutorNode
};

const workflowId = ref<string | null>(null);
const workflowName = ref('');
const workflowCode = ref('');
const saving = ref(false);
const selectedNodeId = ref<string | null>(null);
const isDirty = ref(false);
const loaded = ref(false);

interface FlowNode {
	id: string;
	type: string;
	label: string;
	position: { x: number; y: number };
	data: {
		config: Record<string, any>;
	};
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
	};
}

// 可配置大模型配置列表
const aiProfiles = ref<Eps.profile[]>([]);

// 节点元素集合，包括 Nodes 和 Edges
const elements = ref<(FlowNode | FlowEdge)[]>([]);

// 定义支持拖拽的组件库
const nodeTemplates = [
	{ type: 'start', name: t('开始节点'), desc: t('工作流启动入口'), icon: VideoPlay },
	{ type: 'llm', name: t('LLM 节点'), desc: t('生成文本、总结、格式化'), icon: Cpu },
	{ type: 'tool', name: t('工具节点 (Mock)'), desc: t('简单 Mock 工具响应'), icon: Setting },
	{ type: 'condition', name: t('条件分支'), desc: t('根据变量值走向不同分支'), icon: Operation },
	{ type: 'switch', name: t('分支选择 (Switch)'), desc: t('多分支条件选择流转'), icon: Operation },
	{ type: 'human_input', name: t('人工审批'), desc: t('中断图运行等待人工干预'), icon: UserFilled },
	{ type: 'intent_classifier', name: t('意图分类'), desc: t('大模型意图识别分流'), icon: MagicStick },
	{ type: 'loop_controller', name: t('循环控制'), desc: t('列表/数组循环遍历'), icon: Refresh },
	{ type: 'batch_processor', name: t('并发批处理'), desc: t('大批量数据并发处理'), icon: Files },
	{ type: 'image_generator', name: t('生图节点'), desc: t('大模型文生图'), icon: Picture },
	{ type: 'tool_executor', name: t('工具执行器'), desc: t('执行网页搜索/文件读写'), icon: Setting },
	{ type: 'end', name: t('结束节点'), desc: t('工作流汇聚完结点'), icon: CircleCheck }
];

// 定义画布连线的默认样式
const defaultEdgeOptions = {
	type: 'default',
	animated: true,
	style: { stroke: '#409eff', strokeWidth: 2 }
};

// 当前选中节点的计算属性
const selectedNode = computed(() => {
	if (!selectedNodeId.value) return null;
	return elements.value.find(el => el.id === selectedNodeId.value && !('source' in el)) as FlowNode | undefined;
});

// 除了自身之外的可用目标节点（用于分支设置的路由下拉菜单中）
const availableTargetNodes = computed(() => {
	return elements.value.filter(el => !('source' in el) && el.id !== selectedNodeId.value) as FlowNode[];
});

// 收集当前节点的上游可达变量
const upstreamVariables = computed(() => {
	if (!selectedNode.value) return [];
	const result: { nodeId: string; nodeLabel: string; variableName: string; nodeType: string }[] = [];
	const visited = new Set<string>();
	function traceUpstream(nodeId: string) {
		if (visited.has(nodeId)) return;
		visited.add(nodeId);
		const incomingEdges = elements.value.filter(
			(el: any) => 'source' in el && el.target === nodeId
		) as FlowEdge[];
		for (const edge of incomingEdges) {
			const src = elements.value.find(
				(el: any) => !('source' in el) && el.id === edge.source
			) as FlowNode | undefined;
			if (!src) continue;
			if (src.type === 'start') {
				if (visited.has(src.id)) continue;
				visited.add(src.id);
				// 开始节点提供工作流输入变量
				const inputVars: string[] = (src.data?.config as any)?.inputVariables || [];
				for (const varName of inputVars) {
					if (varName && varName.trim()) {
						result.push({ nodeId: src.id, nodeLabel: src.label, variableName: varName.trim(), nodeType: src.type });
					}
				}
			} else {
				const cfg = src.data?.config || {};
				const outputVar = (cfg as any).outputVariable || '';
				if (outputVar) {
					result.push({ nodeId: src.id, nodeLabel: src.label, variableName: outputVar, nodeType: src.type });
				}
				traceUpstream(src.id);
			}
		}
	}
	traceUpstream(selectedNode.value.id);
	return result;
});

// 变量引用格式提示
const variableSyntaxHints = computed(() => {
	const nodeType = selectedNode.value?.type;
	if (!nodeType) return [];
	const hints: { label: string; syntax: string }[] = [];
	if (['llm', 'image_generator', 'batch_processor', 'end'].includes(nodeType)) {
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

onMounted(() => {
	workflowId.value = (route.query.id as string) || null;
	if (workflowId.value) {
		fetchWorkflowData();
	} else {
		loaded.value = true;
	}
	fetchAiProfiles();

	// 监听键盘按键删除元素
	window.addEventListener('keydown', handleKeyDown);
});

onUnmounted(() => {
	window.removeEventListener('keydown', handleKeyDown);
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

	if (event.key === 'Delete' || event.key === 'Backspace') {
		deleteSelectedElements();
	}
}

function deleteSelectedElements() {
	const nodesToRemove = elements.value.filter(el => !('source' in el) && (el as any).selected);
	const edgesToRemove = elements.value.filter(el => 'source' in el && (el as any).selected);

	if (nodesToRemove.length > 0 || edgesToRemove.length > 0) {
		const nodeIdsToRemove = new Set(nodesToRemove.map(n => n.id));
		const edgeIdsToRemove = new Set(edgesToRemove.map(e => e.id));

		elements.value = elements.value.filter(el => {
			if ('source' in el) {
				return !edgeIdsToRemove.has(el.id) && !nodeIdsToRemove.has(el.source) && !nodeIdsToRemove.has(el.target);
			} else {
				return !nodeIdsToRemove.has(el.id);
			}
		});

		if (selectedNodeId.value && nodeIdsToRemove.has(selectedNodeId.value)) {
			selectedNodeId.value = null;
		}

		ElMessage.success(t('已删除所选元素'));
	}
}

watch(
	elements,
	() => {
		if (loaded.value) {
			isDirty.value = true;
		}
	},
	{ deep: true }
);

async function fetchWorkflowData() {
	try {
		const res = await (service as any).workflow.definition.info({ id: workflowId.value });
		workflowName.value = res.name;
		workflowCode.value = res.code;
		
		// 加载已有的拓扑连线
		if (res.graphJson && res.graphJson !== '{}') {
			const graph = JSON.parse(res.graphJson);
			
			// 转换 JSON 到 Vue Flow 的 elements
			const loadedElements = graph.elements || [];
			// 转换 tool_executor 的 arguments
			loadedElements.forEach((el: any) => {
				if (el.type === 'tool_executor' && el.data?.config) {
					if (el.data.config.arguments && !el.data.config.argumentsJson) {
						el.data.config.argumentsJson = JSON.stringify(el.data.config.arguments, null, 2);
					}
				}
				// 兼容旧数据
				if (el.type === 'start' && el.data?.config && !el.data.config.inputVariables) {
					el.data.config.inputVariables = ['query'];
				}
				if (el.type === 'end' && el.data?.config) {
					if (!el.data.config.outputFormat) {
						el.data.config.outputFormat = el.data.config.outputTemplate ? 'text' : 'json';
					}
					if (!el.data.config.outputFields) {
						el.data.config.outputFields = [];
					}
				}
				if (el.type === 'llm' && el.data?.config && !el.data.config.jsonFields) {
					el.data.config.jsonFields = [];
				}
			});
			elements.value = loadedElements;
		} else {
			// 初始化一个“开始”和“结束”的默认节点
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

// 画布放置时实例化新节点
function onDrop(event: DragEvent) {
	const type = event.dataTransfer?.getData('application/vueflow');
	if (!type) return;

	// 开始/结束节点全局唯一，已存在时阻止添加
	if (type === 'start' || type === 'end') {
		const exists = elements.value.some(el => !('source' in el) && el.type === type);
		if (exists) {
			ElMessage.warning(t(type === 'start' ? '开始节点已存在，画布中仅允许一个' : '结束节点已存在，画布中仅允许一个'));
			return;
		}
	}

	// 计算在画布内的放置坐标
	const react = event.currentTarget as HTMLElement;
	const bounds = react.getBoundingClientRect();
	const x = event.clientX - bounds.left - 50;
	const y = event.clientY - bounds.top - 20;

	const id = `node_${type}_${Date.now()}`;
	const label = getNextLabel(type);

	// 初始化节点特定 config
	let config: Record<string, any> = {};
	if (type === 'llm') {
		config = { modelProfileCode: '', promptTemplate: '', outputFormat: 'text', jsonFields: [], outputVariable: getUniqueOutputVar(label, 'output') };
	} else if (type === 'tool') {
		config = { toolName: '', outputVariable: getUniqueOutputVar(label, 'tool_result') };
	} else if (type === 'condition') {
		config = { expression: '', trueRoute: '', falseRoute: '' };
	} else if (type === 'switch') {
		config = { variable: '', cases: [], defaultRoute: '' };
	} else if (type === 'human_input') {
		config = { message: '', outputVariable: getUniqueOutputVar(label, 'approval_status') };
	} else if (type === 'intent_classifier') {
		config = { modelProfileCode: '', intents: [], defaultRoute: '' };
	} else if (type === 'loop_controller') {
		config = { listVariable: 'list_variable', itemVariable: 'loop_item', loopBodyRoute: '', exitRoute: '' };
	} else if (type === 'batch_processor') {
		config = { batchListVariable: 'batch_list_variable', actionTemplate: { type: 'llm', config: { modelProfileCode: '', promptTemplate: '' } }, concurrencyLimit: 5, outputVariable: getUniqueOutputVar(label, 'batch_results') };
	} else if (type === 'image_generator') {
		config = { modelProfileCode: '', promptTemplate: '', size: '1024x1024', outputVariable: getUniqueOutputVar(label, 'image_url') };
	} else if (type === 'tool_executor') {
		config = { toolCode: '', argumentsJson: '{}', outputVariable: getUniqueOutputVar(label, 'tool_result') };
	} else if (type === 'end') {
		config = { outputFormat: 'json', outputFields: [] };
	}

	const newNode = {
		id,
		type,
		label,
		position: { x, y },
		data: { config }
	};

	elements.value.push(newNode);
}

function getTypeName(type: string) {
	if (type === 'start') return t('开始');
	if (type === 'end') return t('结束');
	if (type === 'llm') return t('LLM 节点');
	if (type === 'tool') return t('工具节点');
	if (type === 'condition') return t('条件分支');
	if (type === 'switch') return t('分支选择');
	if (type === 'human_input') return t('人工审批');
	if (type === 'intent_classifier') return t('意图分类');
	if (type === 'loop_controller') return t('循环控制');
	if (type === 'batch_processor') return t('并发批处理');
	if (type === 'image_generator') return t('生图节点');
	if (type === 'tool_executor') return t('工具执行器');
	return t('未知节点');
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
	const newEdge = {
		id: `edge_${params.source}_${params.target}`,
		source: params.source || '',
		target: params.target || '',
		animated: true,
		style: { stroke: '#409eff', strokeWidth: 2 }
	};
	elements.value.push(newEdge);
}

function onPaneReady(instance: any) {
	instance.fitView();
}

function onNodeClick(event: { node: any }) {
	selectedNodeId.value = event.node.id;
}

function onPaneClick() {
	selectedNodeId.value = null;
}

function deleteSelectedNode() {
	if (!selectedNodeId.value) return;
	// 移除关联的连线
	elements.value = elements.value.filter(el => {
		if ('source' in el) {
			const edge = el as FlowEdge;
			return edge.id !== selectedNodeId.value && edge.source !== selectedNodeId.value && edge.target !== selectedNodeId.value;
		}
		return el.id !== selectedNodeId.value;
	});
	selectedNodeId.value = null;
}

// 将 Vue Flow 画布信息转换打包为后端标准工作流 JSON 格式并存储
async function saveWorkflow() {
	if (!workflowId.value) return;
	saving.value = true;
	try {
		// 1. 拆分连线与节点 (TS-safe 属性检查)
		const nodes = elements.value.filter(el => !('source' in el)) as FlowNode[];
		const edges = elements.value.filter(el => 'source' in el) as FlowEdge[];

		// 2. 检查图结构完整性并给以提示
		const warnings: string[] = [];
		const startNodes = nodes.filter(n => n.type === 'start');
		if (startNodes.length === 0) {
			warnings.push(t('工作流缺失“开始节点”，请在画布中添加唯一入口！'));
		} else if (startNodes.length > 1) {
			warnings.push(t('工作流存在多个“开始节点”，请在画布中保留唯一入口！'));
		}

		// 检查 Switch 分支节点是否配置完整
		const switchNodes = nodes.filter(n => n.type === 'switch');
		for (const n of switchNodes) {
			const conf = n.data?.config || {};
			if (!conf.variable || !conf.variable.trim()) {
				warnings.push(t('节点“') + (n.label || n.id) + t('”未指定匹配变量名！'));
			}
			if (!conf.defaultRoute) {
				warnings.push(t('节点“') + (n.label || n.id) + t('”未指定默认路由！'));
			}
			const cases = conf.cases || [];
			const seenCaseVals = new Set<string>();
			for (const c of cases) {
				if (!c.value || !c.value.trim()) {
					warnings.push(t('节点“') + (n.label || n.id) + t('”存在空白的 Case 匹配值！'));
				}
				if (!c.targetRoute) {
					warnings.push(t('节点“') + (n.label || n.id) + t('”存在未选择目标路由的 Case 分支！'));
				}
				if (c.value) {
					if (seenCaseVals.has(c.value.trim())) {
						warnings.push(t('节点“') + (n.label || n.id) + t('”中存在重复的 Case 匹配值：') + c.value.trim());
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
		const isolatedNodes = nodes.filter(n => n.type !== 'start' && n.type !== 'end' && !connectedNodeIds.has(n.id));
		if (isolatedNodes.length > 0) {
			warnings.push(t('发现孤立的工作节点：') + isolatedNodes.map(n => n.label || n.id).join(', ') + t('，请建立输入和输出连线！'));
		}

		// 检查模型节点是否已选择 Profile
		const modelRequiredTypes = ['llm', 'intent_classifier', 'batch_processor', 'image_generator'];
		const missingProfileNodes = nodes.filter(
			n => modelRequiredTypes.includes(n.type) && !(n.data?.config as any)?.modelProfileCode?.trim()
		);
		if (missingProfileNodes.length > 0) {
			warnings.push(
				t('以下节点未选择模型 Profile：') + missingProfileNodes.map(n => n.label || n.id).join(', ') + t('，请先在配置面板中选择模型！')
			);
		}

		// 检查是否存在重复的输出变量名
		const varNameToNodes = new Map<string, string[]>();
		for (const n of nodes) {
			const outVar = (n.data?.config as any)?.outputVariable?.trim();
			if (outVar) {
				const list = varNameToNodes.get(outVar) || [];
				list.push(n.label || n.id);
				varNameToNodes.set(outVar, list);
			}
		}
		const duplicates = [...varNameToNodes.entries()].filter(([, ns]) => ns.length > 1);
		if (duplicates.length > 0) {
			const detail = duplicates.map(([varName, nodeNames]) => `${varName} (${nodeNames.join(', ')})`).join('; ');
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
		const graphPayload = {
			elements: elements.value,
			nodes: nodes.map(n => {
				const conf = { ...(n.data?.config || {}) };
				if (n.type === 'tool_executor') {
					try {
						conf.arguments = JSON.parse(conf.argumentsJson || '{}');
					} catch (e) {
						conf.arguments = {};
					}
				}
				return {
					id: n.id,
					type: n.type,
					name: n.label,
					config: conf
				};
			}),
			edges: edges.map(e => ({
				source: e.source,
				target: e.target,
				type: e.type || 'direct',
				condition: e.data?.condition || ''
			}))
		};

		// 4. 更新定义记录
		await (service as any).workflow.definition.update({
			id: Number(workflowId.value),
			code: workflowCode.value,
			name: workflowName.value,
			graphJson: JSON.stringify(graphPayload)
		});

		ElMessage.success(t('工作流保存成功'));
		isDirty.value = false;
	} catch (err: any) {
		ElMessage.error(t('保存失败: ') + (err.message || err));
	} finally {
		saving.value = false;
	}
}

function goBack() {
	if (!isDirty.value) {
		router.push('/workflow/definition');
		return;
	}
	ElMessageBox.confirm(
		t('是否有未保存的更改？确认离开编辑页面吗？'),
		t('提示'),
		{
			confirmButtonText: t('确定'),
			cancelButtonText: t('取消'),
			type: 'warning'
		}
	).then(() => {
		router.push('/workflow/definition');
	}).catch(() => {});
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

.editor-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	height: 60px;
	padding: 0 20px;
	background-color: #fff;
	border-bottom: 1px solid var(--el-border-color-light);
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
	z-index: 10;

	&__left {
		display: flex;
		align-items: center;
		gap: 12px;

		.workflow-title {
			font-size: 16px;
			font-weight: 600;
			color: var(--el-text-color-primary);
		}
	}
}

.editor-body {
	display: flex;
	flex: 1;
	width: 100%;
	overflow: hidden;
}

.node-sidebar {
	width: 280px;
	background-color: #fff;
	border-right: 1px solid var(--el-border-color-light);
	padding: 20px;
	display: flex;
	flex-direction: column;
	gap: 16px;

	.sidebar-title {
		font-size: 15px;
		font-weight: 600;
		color: var(--el-text-color-primary);
	}

	.sidebar-description {
		font-size: 12px;
		color: var(--el-text-color-placeholder);
		margin-top: -8px;
	}
}

.node-templates {
	display: flex;
	flex-direction: column;
	gap: 12px;
	overflow-y: auto;
}

.node-template-item {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 12px;
	background-color: var(--el-fill-color-blank);
	border: 1px dashed var(--el-border-color);
	border-radius: 6px;
	cursor: grab;
	transition: all 0.3s;

	&:hover {
		border-color: var(--el-color-primary);
		box-shadow: 0 4px 10px rgba(64, 158, 255, 0.08);
	}

	.template-icon {
		font-size: 20px;
		color: var(--el-text-color-secondary);
	}

	.template-name {
		font-size: 13px;
		font-weight: 600;
		color: var(--el-text-color-primary);
	}

	.template-desc {
		font-size: 11px;
		color: var(--el-text-color-placeholder);
		margin-top: 2px;
	}

	// 节点特有色彩发光
	&--start {
		border-left: 4px solid var(--el-color-success);
	}
	&--llm {
		border-left: 4px solid var(--el-color-primary);
	}
	&--tool {
		border-left: 4px solid #8a2be2;
	}
	&--condition {
		border-left: 4px solid var(--el-color-warning);
	}
	&--switch {
		border-left: 4px solid #e6a23c;
	}
	&--human_input {
		border-left: 4px solid var(--el-color-info);
	}
	&--intent_classifier {
		border-left: 4px solid #20b2aa;
	}
	&--loop_controller {
		border-left: 4px solid #d2691e;
	}
	&--batch_processor {
		border-left: 4px solid #00ced1;
	}
	&--image_generator {
		border-left: 4px solid #ff69b4;
	}
	&--tool_executor {
		border-left: 4px solid #8a2be2;
	}
	&--end {
		border-left: 4px solid var(--el-color-danger);
	}
}

.canvas-wrapper {
	flex: 1;
	height: 100%;
	position: relative;
	background-color: #f7f9fb;
}

.config-panel-empty {
	width: 320px;
	background-color: #fff;
	border-left: 1px solid var(--el-border-color-light);
	display: flex;
	align-items: center;
	justify-content: center;
}
</style>
