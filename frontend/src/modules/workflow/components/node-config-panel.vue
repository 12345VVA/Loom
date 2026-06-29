<template>
	<div
		class="config-panel"
		role="complementary"
		aria-label="节点配置"
		:style="{ width: panelWidth + 'px' }"
	>
		<div class="panel-resizer" @mousedown="startResize"></div>
		<div class="panel-header">
			<div
				class="panel-header__title"
				@dblclick="startEditTitle"
				style="flex: 1; min-width: 0"
			>
				<el-icon v-if="nodeIcon" class="panel-header__icon"
					><component :is="nodeIcon"
				/></el-icon>
				<template v-if="isEditingTitle">
					<el-input
						ref="titleInputRef"
						v-model="selectedNode.label"
						size="small"
						style="flex: 1"
						@blur="isEditingTitle = false"
						@keyup.enter="isEditingTitle = false"
					/>
				</template>
				<template v-else>
					<span
						style="
							cursor: pointer;
							user-select: none;
							overflow: hidden;
							text-overflow: ellipsis;
							white-space: nowrap;
						"
						:title="`ID: ${selectedNode.id} (双击重命名)`"
					>
						{{ selectedNode.label || $t('未命名节点') }}
					</span>
				</template>
			</div>
			<div class="panel-header__actions">
				<el-tooltip v-if="canTestNode" :content="$t('测试节点')" placement="top">
					<el-button link type="success" :icon="VideoPlay" @click="handleTestNode" />
				</el-tooltip>
				<el-tooltip :content="$t('删除节点')" placement="top">
					<el-button link type="danger" :icon="Delete" @click="emit('delete')" />
				</el-tooltip>
				<el-button link :icon="Close" @click="emit('close')" />
			</div>
		</div>

		<el-scrollbar class="panel-content" ref="scrollbarRef">
			<el-form :model="selectedNode.data" label-position="top">
				<!-- 统一的节点输入配置 (Strict Mode) -->
				<node-inputs-editor
					v-if="selectedNode.type !== 'start'"
					:key="selectedNode.id"
					v-model="selectedNode.data.config.inputs"
					:upstream-vars="upstreamOutputVarsOriginal"
				/>

				<!-- 节点级失败重试（除 start/end 外的执行类节点） -->
				<node-config-section
					v-if="selectedNode.type !== 'start' && selectedNode.type !== 'end'"
					:title="$t('失败重试')"
					:tooltip="$t('节点执行失败时按指数退避自动重试；留空则使用服务端全局默认')"
					:default-expanded="false"
				>
					<el-form-item :label="$t('最大尝试次数')" style="margin-bottom: 0">
						<el-input-number
							v-model="selectedNode.data.config.retryMaxAttempts"
							:min="1"
							:max="10"
							:step="1"
							controls-position="right"
							style="width: 100%"
						/>
						<div class="field-hint">
							{{ $t('含首次执行；1 = 不重试。留空使用服务端默认') }}
						</div>
					</el-form-item>
					<el-form-item :label="$t('退避基数(秒)')" style="margin-top: 18px; margin-bottom: 0">
						<el-input-number
							v-model="selectedNode.data.config.retryBackoffBase"
							:min="0.5"
							:max="60"
							:step="0.5"
							controls-position="right"
							style="width: 100%"
						/>
						<div class="field-hint">
							{{ $t('指数退避：第 N 次重试等待 = 基数 × 2^(N-1) 秒') }}
						</div>
					</el-form-item>
				</node-config-section>

				<!-- 动态载入对应节点的表单配置组件 -->
				<div :key="selectedNode.id">
					<component
						:is="CONFIG_COMPONENTS[selectedNode.type]"
						v-if="CONFIG_COMPONENTS[selectedNode.type]"
						v-model="selectedNode.data.config"
						:node-id="selectedNode.id"
						:profiles="filteredProfiles"
						:available-target-nodes="
							selectedNode.type === 'loop_controller' ||
							selectedNode.type === 'batch_processor'
								? filteredBodyTargetNodes
								: availableTargetNodes
						"
					/>
				</div>
			</el-form>
		</el-scrollbar>
	</div>
</template>

<script setup lang="ts">
import { computed, provide, inject, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { cloneDeep, isEqual } from 'lodash-es';
import {
	Check,
	Edit,
	Close,
	MagicStick,
	SwitchButton,
	CaretRight,
	Delete,
	VideoPlay
} from '@element-plus/icons-vue';
import {
	UNTESTABLE_NODE_TYPES,
	OPEN_NODE_TEST_DIALOG_KEY,
	UPSTREAM_VARIABLES_KEY,
	LOOP_CONTEXT_VARS_KEY,
	UPSTREAM_OUTPUT_VARS_KEY,
	VARIABLE_SYNTAX_HINTS_KEY,
	SECTION_COLLAPSE_STATE_KEY,
	CONFIG_PANEL_NODE_ID_KEY
} from './constants';
import type { ElScrollbar } from 'element-plus';
import { getNodeMeta } from '../utils/node-type-registry';

// 导入所有配置组件
import StartConfig from './node-configs/start-config.vue';
import EndConfig from './node-configs/end-config.vue';
import LlmConfig from './node-configs/llm-config.vue';
import ToolConfig from './node-configs/tool-config.vue';
import ConditionConfig from './node-configs/condition-config.vue';
import SwitchConfig from './node-configs/switch-config.vue';
import HumanInputConfig from './node-configs/human-input-config.vue';
import IntentClassifierConfig from './node-configs/intent-classifier-config.vue';
import LoopControllerConfig from './node-configs/loop-controller-config.vue';
import BatchProcessorConfig from './node-configs/batch-processor-config.vue';
import ImageGeneratorConfig from './node-configs/image-generator-config.vue';
import ToolExecutorConfig from './node-configs/tool-executor-config.vue';
import LoopBodyGroupConfig from './node-configs/loop-body-group-config.vue';
import VariableAssignmentConfig from './node-configs/variable-assignment-config.vue';
import VariableTransformConfig from './node-configs/variable-transform-config.vue';
import NodeInputsEditor from './node-inputs-editor.vue';
import NodeConfigSection from './node-configs/node-config-section.vue';

const { t } = useI18n();

const props = defineProps<{
	selectedNode: any;
	upstreamVariables: any[];
	variableSyntaxHints: any[];
	availableTargetNodes: any[];
	filteredBodyTargetNodes: any[];
	aiProfiles: any[];
	workflowId?: string | number;
}>();

const emit = defineEmits(['delete', 'close', 'update:width']);

const CONFIG_COMPONENTS: Record<string, any> = {
	start: StartConfig,
	end: EndConfig,
	llm: LlmConfig,
	tool: ToolConfig,
	condition: ConditionConfig,
	switch: SwitchConfig,
	human_input: HumanInputConfig,
	intent_classifier: IntentClassifierConfig,
	loop_controller: LoopControllerConfig,
	batch_processor: BatchProcessorConfig,
	image_generator: ImageGeneratorConfig,
	tool_executor: ToolExecutorConfig,
	loop_body_group: LoopBodyGroupConfig,
	variable_assignment: VariableAssignmentConfig,
	variable_transform: VariableTransformConfig
};

// 节点类型 → 所需的 AI 模型类型映射
const NODE_MODEL_TYPE_MAP: Record<string, string> = {
	llm: 'chat',
	intent_classifier: 'chat',
	image_generator: 'image'
};

const nodeIcon = computed(() => getNodeMeta(props.selectedNode?.type).icon);

const openNodeTestDialog = inject(OPEN_NODE_TEST_DIALOG_KEY);

const canTestNode = computed(() => {
	return props.selectedNode?.type && !UNTESTABLE_NODE_TYPES.includes(props.selectedNode.type);
});

function handleTestNode() {
	if (openNodeTestDialog && props.selectedNode) {
		openNodeTestDialog(props.selectedNode.id);
	}
}

// 滚动条引用
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();

// 监听选中节点变化，重置滚动位置和编辑状态
watch(
	() => props.selectedNode?.id,
	() => {
		scrollbarRef.value?.setScrollTop(0);
		isEditingTitle.value = false;
	}
);

// 标题编辑逻辑
const isEditingTitle = ref(false);
const titleInputRef = ref();

function startEditTitle() {
	isEditingTitle.value = true;
	nextTick(() => {
		titleInputRef.value?.focus();
	});
}

// 面板宽度调整
const defaultWidth = 420;
const storageKey = computed(() => `loom_editor_panel_width_${props.workflowId || 'default'}`);
const panelWidth = ref(
	Math.max(parseInt(localStorage.getItem(storageKey.value) || String(defaultWidth)), defaultWidth)
);
let isResizing = false;
let startX = 0;
let startWidth = 0;

function startResize(e: MouseEvent) {
	isResizing = true;
	startX = e.clientX;
	startWidth = panelWidth.value;
	document.addEventListener('mousemove', onMouseMove);
	document.addEventListener('mouseup', onMouseUp);
	document.body.style.cursor = 'ew-resize';
	document.body.style.userSelect = 'none';
}

function onMouseMove(e: MouseEvent) {
	if (!isResizing) return;
	const delta = startX - e.clientX;
	let newWidth = startWidth + delta;
	if (newWidth < 280) newWidth = 280;
	if (newWidth > 600) newWidth = 600;
	panelWidth.value = newWidth;
}

function onMouseUp() {
	if (isResizing) {
		isResizing = false;
		document.removeEventListener('mousemove', onMouseMove);
		document.removeEventListener('mouseup', onMouseUp);
		document.body.style.cursor = '';
		document.body.style.userSelect = '';
		localStorage.setItem(storageKey.value, String(panelWidth.value));
		emit('update:width', panelWidth.value);
	}
}

onBeforeUnmount(() => {
	document.removeEventListener('mousemove', onMouseMove);
	document.removeEventListener('mouseup', onMouseUp);
});

// 根据当前选中节点类型过滤模型 Profile 列表
const filteredProfiles = computed(() => {
	const nodeType = props.selectedNode?.type;
	if (!nodeType) return props.aiProfiles;
	const requiredType = NODE_MODEL_TYPE_MAP[nodeType];
	if (!requiredType) return props.aiProfiles;
	return props.aiProfiles.filter(p => p.modelType === requiredType);
});

// 递归展平 JSON 字段树
function flattenTreeFields(
	fields: any[],
	prefix: string,
	displayPrefix: string,
	nodeLabel: string,
	nodeId: string
): { key: string; display: string; refText: string; nodeLabel: string; nodeId: string; variableName: string }[] {
	const result: any[] = [];
	if (!fields || !Array.isArray(fields)) return result;

	for (const field of fields) {
		if (!field.name || !field.name.trim()) continue;

		const name = field.name.trim();
		const currentRefPath = `${prefix}.${name}`;
		const currentDisplayPath = `${displayPrefix}.${name}`;
		const refText = getVariableRefText(currentRefPath);

		result.push({
			key: `${nodeId}_${currentRefPath}`,
			display: `{${currentDisplayPath}}`,
			refText: refText,
			nodeLabel: `${nodeLabel} → .${name}`,
			nodeId: nodeId,
			variableName: currentRefPath
		});

		if (field.children && Array.isArray(field.children) && field.children.length > 0) {
			if (field.type === 'array_object') {
				result.push(
					...flattenTreeFields(
						field.children,
						`${currentRefPath}.0`,
						`${currentDisplayPath}.[Item]`,
						nodeLabel,
						nodeId
					)
				);
			} else {
				result.push(
					...flattenTreeFields(
						field.children,
						currentRefPath,
						currentDisplayPath,
						nodeLabel,
						nodeId
					)
				);
			}
		}
	}
	return result;
}

// 缓存上游变量避免高频引发组件更新
const cachedUpstreamVariables = ref<any[]>([]);

watch(
	() => props.upstreamVariables,
	(newVal) => {
		if (!isEqual(newVal, cachedUpstreamVariables.value)) {
			cachedUpstreamVariables.value = cloneDeep(newVal || []);
		}
	},
	{ immediate: true, deep: true }
);

// 展平上游变量：对 LLM JSON 输出模式的节点，额外展示子字段
const flattenedVariables = computed(() => {
	const result: { key: string; display: string; refText: string; nodeLabel: string; nodeId: string; variableName: string }[] = [];
	for (const v of cachedUpstreamVariables.value) {
		const baseRef = getVariableRefText(v.variableName);
		result.push({
			key: `${v.nodeId}_${v.variableName}`,
			display: `{${v.variableName}}`,
			refText: baseRef,
			nodeLabel: v.nodeLabel,
			nodeId: v.nodeId,
			variableName: v.variableName
		});

		// 如果上游节点是 LLM 且 JSON 输出模式，递归展开其 jsonFields
		if (v.nodeType === 'llm' && v.jsonFields && Array.isArray(v.jsonFields)) {
			result.push(
				...flattenTreeFields(
					v.jsonFields,
					v.variableName,
					v.variableName,
					v.nodeLabel,
					v.nodeId
				)
			);
		}
	}
	return result;
});

// 循环上下文变量（由 editor.vue 在 group 内节点注入 _isLoopContext 标记）
const loopContextVars = computed(() =>
	flattenedVariables.value.filter(v => {
		const src = cachedUpstreamVariables.value.find(u => `${u.nodeId}_${u.variableName}` === v.key);
		return src?._isLoopContext === true;
	})
);

// 真实的全局上游输出变量，传递给 node-inputs-editor 供用户选择映射
const upstreamOutputVarsOriginal = computed(() => {
	const loopKeys = new Set(loopContextVars.value.map(v => v.key));
	return flattenedVariables.value.filter(v => !loopKeys.has(v.key));
});

// 严格模式：只提供本节点定义的局部 inputs 给子组件
const localInputsVars = computed(() => {
	const inputs = props.selectedNode?.data?.config?.inputs || [];
	return inputs.map((inp: any) => ({
		key: inp.name,
		display: inp.name,
		nodeId: props.selectedNode?.id,
		nodeLabel: '本节点输入',
		variableName: inp.name,
		nodeType: 'local',
		refText: getVariableRefText(inp.name)
	}));
});

// 向下提供变量上下文，供底层组件直接引用（如 cl-variable-input, cl-editor-markdown）
provide(UPSTREAM_VARIABLES_KEY, flattenedVariables);
provide(LOOP_CONTEXT_VARS_KEY, loopContextVars);
provide(UPSTREAM_OUTPUT_VARS_KEY, localInputsVars);
provide(
	VARIABLE_SYNTAX_HINTS_KEY,
	computed(() => props.variableSyntaxHints)
);

// 节点配置区域折叠状态持久化（跨节点切换保持）
const sectionCollapseState = ref<Map<string, boolean>>(new Map());
provide(SECTION_COLLAPSE_STATE_KEY, sectionCollapseState);

// 当前选中节点 ID，供 node-config-section 生成唯一存储键
provide(
	CONFIG_PANEL_NODE_ID_KEY,
	computed(() => props.selectedNode?.id || '')
);

function getVariableRefText(varName: string): string {
	const nodeType = props.selectedNode?.type;
	if (nodeType === 'condition' || nodeType === 'tool_executor') {
		return `variables.${varName}`;
	}
	return `{${varName}}`;
}
</script>

<style lang="scss" scoped>
.config-panel {
	position: absolute;
	top: 0;
	right: 0;
	bottom: 0;
	width: 420px;
	background-color: #fff;
	border-left: 1px solid var(--el-border-color-light);
	box-shadow: -4px 0 16px rgba(0, 0, 0, 0.06);
	display: flex;
	flex-direction: column;
	z-index: 10;

	.panel-resizer {
		position: absolute;
		left: -4px;
		top: 0;
		bottom: 0;
		width: 8px;
		cursor: ew-resize;
		z-index: 11;

		&:hover {
			background-color: rgba(64, 158, 255, 0.2);
		}
	}

	@media (max-width: 1200px) {
		width: min(360px, 40vw) !important;
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px;
		border-bottom: 1px solid var(--el-border-color-light);

		&__title {
			font-size: 15px;
			font-weight: 600;
			display: flex;
			align-items: center;
			gap: 6px;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}

		&__icon {
			font-size: 16px;
			color: var(--el-color-primary);
		}

		&__actions {
			display: flex;
			align-items: center;
			gap: 4px;
		}
	}

	.panel-content {
		flex: 1;
		padding: 0;
		background: #fafafa;
	}
}

.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}
</style>
