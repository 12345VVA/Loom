<template>
	<div class="config-panel">
		<div class="panel-header">
			<div class="panel-header__title">{{ $t('参数配置') }}</div>
			<el-button link type="danger" :icon="Delete" @click="emit('delete')">
				{{ $t('删除节点') }}
			</el-button>
		</div>

		<el-scrollbar class="panel-content" @focusin="onConfigPanelFocusIn">
			<el-form :model="selectedNode.data" label-position="top">
				<el-form-item :label="$t('节点ID')">
					<el-input :model-value="selectedNode.id" disabled />
				</el-form-item>
				<el-form-item :label="$t('节点名称')">
					<el-input v-model="selectedNode.label" />
				</el-form-item>

				<el-divider />

				<!-- 变量引用面板 -->
				<div v-if="upstreamVariables.length > 0" class="variable-ref-panel">
					<!-- 循环上下文 -->
					<div v-if="loopContextVars.length > 0" class="variable-section">
						<div class="variable-section-title">{{ $t('循环上下文') }}</div>
						<div class="variable-ref-list">
							<el-tag
								v-for="v in loopContextVars"
								:key="v.key"
								size="small"
								effect="plain"
								class="variable-tag variable-tag--loop"
								@click="insertVariableToField(v.refText)"
							>
								{{ v.display }}
								<span class="variable-source">{{ v.nodeLabel }}</span>
							</el-tag>
						</div>
					</div>
					<!-- 上游输出 -->
					<div v-if="upstreamOutputVars.length > 0" class="variable-section">
						<div class="variable-section-title">{{ $t('上游输出') }}</div>
						<div class="variable-ref-list">
							<el-tag
								v-for="v in upstreamOutputVars"
								:key="v.key"
								size="small"
								effect="plain"
								class="variable-tag"
								@click="insertVariableToField(v.refText)"
							>
								{{ v.display }}
								<span class="variable-source">{{ v.nodeLabel }}</span>
							</el-tag>
						</div>
					</div>
					<!-- 语法提示 -->
					<div v-if="variableSyntaxHints.length > 0" class="variable-ref-hint">
						<div v-for="h in variableSyntaxHints" :key="h.label" class="hint-item">
							<span class="hint-label">{{ h.label }}:</span>
							<code>{{ h.syntax }}</code>
						</div>
					</div>
				</div>

				<!-- 动态载入对应节点的表单配置组件 -->
				<component
					:is="CONFIG_COMPONENTS[selectedNode.type]"
					v-if="CONFIG_COMPONENTS[selectedNode.type]"
					:key="selectedNode.id"
					v-model="selectedNode.data.config"
					:profiles="filteredProfiles"
					:available-target-nodes="selectedNode.type === 'loop_controller' || selectedNode.type === 'batch_processor'
						? filteredBodyTargetNodes
						: availableTargetNodes"
				/>
			</el-form>
		</el-scrollbar>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { Delete } from '@element-plus/icons-vue';

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

const { t } = useI18n();

const props = defineProps<{
	selectedNode: any;
	upstreamVariables: any[];
	variableSyntaxHints: any[];
	availableTargetNodes: any[];
	filteredBodyTargetNodes: any[];
	aiProfiles: any[];
}>();

const emit = defineEmits(['delete']);

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
	image_generator: 'image',
};

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
): { key: string; display: string; refText: string; nodeLabel: string }[] {
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
			nodeLabel: `${nodeLabel} → .${name}`
		});

		if (field.children && Array.isArray(field.children) && field.children.length > 0) {
			if (field.type === 'array_object') {
				result.push(...flattenTreeFields(field.children, `${currentRefPath}.0`, `${currentDisplayPath}.[Item]`, nodeLabel, nodeId));
			} else {
				result.push(...flattenTreeFields(field.children, currentRefPath, currentDisplayPath, nodeLabel, nodeId));
			}
		}
	}
	return result;
}

// 展平上游变量：对 LLM JSON 输出模式的节点，额外展示子字段
const flattenedVariables = computed(() => {
	const result: { key: string; display: string; refText: string; nodeLabel: string }[] = [];
	for (const v of props.upstreamVariables) {
		const baseRef = getVariableRefText(v.variableName);
		result.push({
			key: `${v.nodeId}_${v.variableName}`,
			display: `{${v.variableName}}`,
			refText: baseRef,
			nodeLabel: v.nodeLabel
		});

		// 如果上游节点是 LLM 且 JSON 输出模式，递归展开其 jsonFields
		if (v.nodeType === 'llm' && v.jsonFields && Array.isArray(v.jsonFields)) {
			result.push(...flattenTreeFields(v.jsonFields, v.variableName, v.variableName, v.nodeLabel, v.nodeId));
		}
	}
	return result;
});

// 循环上下文变量（由 editor.vue 在 group 内节点注入 _isLoopContext 标记）
const loopContextVars = computed(() => flattenedVariables.value.filter(v => {
	const src = props.upstreamVariables.find(u => `${u.nodeId}_${u.variableName}` === v.key);
	return src?._isLoopContext === true;
}));

// 上游输出变量（非循环上下文）
const upstreamOutputVars = computed(() => {
	const loopKeys = new Set(loopContextVars.value.map(v => v.key));
	return flattenedVariables.value.filter(v => !loopKeys.has(v.key));
});

// ---------- 变量插入逻辑 ----------

// 记录最后获得焦点的输入框
const lastFocusedInput = ref<HTMLTextAreaElement | HTMLInputElement | null>(null);
// 记住最后聚焦的 Markdown 编辑器绑定的 config 字段路径
const lastFocusedFieldInfo = ref<{ configKey: string; cursorPos: number } | null>(null);

// 节点类型 → 使用 Markdown 编辑器的 config 字段列表
const MARKDOWN_FIELDS_MAP: Record<string, string[]> = {
	llm: ['promptTemplate'],
	image_generator: ['promptTemplate'],
	end: ['outputTemplate']
};

function onConfigPanelFocusIn(event: FocusEvent) {
	const target = event.target;
	if (target instanceof HTMLTextAreaElement || (target instanceof HTMLInputElement && target.type === 'text')) {
		lastFocusedInput.value = target as any;
		const fieldInfo = detectMarkdownEditorField(target as HTMLElement);
		if (fieldInfo) {
			lastFocusedFieldInfo.value = {
				configKey: fieldInfo,
				cursorPos: (target as any).selectionStart ?? 0
			};
		} else {
			lastFocusedFieldInfo.value = null;
		}
	}
}

// 实时追踪游标位置
function onSelectionChange() {
	const el = lastFocusedInput.value;
	if (el && document.body.contains(el) && lastFocusedFieldInfo.value) {
		lastFocusedFieldInfo.value.cursorPos = el.selectionStart ?? 0;
	}
}
document.addEventListener('selectionchange', onSelectionChange);
onUnmounted(() => document.removeEventListener('selectionchange', onSelectionChange));

// 检测元素是否处于 cl-editor-markdown 内部，返回对应的 config 字段名
function detectMarkdownEditorField(el: HTMLElement): string | null {
	// 向上查找 cl-editor-markdown 容器
	let node: HTMLElement | null = el;
	while (node && node !== document.body) {
		if (node.classList && node.classList.contains('cl-editor-markdown')) {
			break;
		}
		node = node.parentElement;
	}
	if (!node || !node.classList.contains('cl-editor-markdown')) return null;

	// 通过 el-form-item label 推断字段名
	let formItem: HTMLElement | null = el;
	while (formItem && formItem !== document.body) {
		if (formItem.classList && formItem.classList.contains('el-form-item')) {
			break;
		}
		formItem = formItem.parentElement;
	}
	if (!formItem) return null;

	const nodeType = props.selectedNode?.type;
	const markdownFields = MARKDOWN_FIELDS_MAP[nodeType] || [];
	if (markdownFields.length === 0) return null;
	// 如果只有一个 Markdown 字段，直接返回
	if (markdownFields.length === 1) return markdownFields[0];

	// 多个 Markdown 字段时，通过 label 推断
	const labelEl = formItem.querySelector('.el-form-item__label');
	if (labelEl) {
		const text = labelEl.textContent?.trim() || '';
		if (text.toLowerCase().includes('prompt') || text.toLowerCase().includes('提示词')) return 'promptTemplate';
		if (text.toLowerCase().includes('输出') || text.toLowerCase().includes('output')) return 'outputTemplate';
	}

	return markdownFields[0];
}

function getVariableRefText(varName: string): string {
	const nodeType = props.selectedNode?.type;
	if (nodeType === 'condition' || nodeType === 'tool_executor') {
		return `variables.${varName}`;
	}
	return `{${varName}}`;
}

// 支持嵌套路径的取值/赋值
function getNestedValue(obj: any, path: string): any {
	const parts = path.split('.');
	let current = obj;
	for (const part of parts) {
		if (current == null || typeof current !== 'object') return undefined;
		current = current[part];
	}
	return current;
}

function setNestedValue(obj: any, path: string, value: any) {
	const parts = path.split('.');
	let current = obj;
	for (let i = 0; i < parts.length - 1; i++) {
		if (current[parts[i]] == null || typeof current[parts[i]] !== 'object') {
			current[parts[i]] = {};
		}
		current = current[parts[i]];
	}
	current[parts[parts.length - 1]] = value;
}

function insertVariableToField(refText: string) {
	// 优先尝试插入到 Markdown 编辑器绑定的 config 字段
	if (lastFocusedFieldInfo.value) {
		const config = props.selectedNode?.data?.config;
		if (config) {
			const key = lastFocusedFieldInfo.value.configKey;
			const currentVal = getNestedValue(config, key) || '';
			const pos = lastFocusedFieldInfo.value.cursorPos;
			const newVal = currentVal.slice(0, pos) + refText + currentVal.slice(pos);
			setNestedValue(config, key, newVal);
			lastFocusedFieldInfo.value.cursorPos = pos + refText.length;
			ElMessage.success(t('已插入: ') + refText);
			return;
		}
	}

	// 其次尝试原生 input/textarea 插入
	const el = lastFocusedInput.value;
	if (el && document.body.contains(el)) {
		const start = el.selectionStart ?? el.value.length;
		const end = el.selectionEnd ?? el.value.length;
		el.setRangeText(refText, start, end, 'end');
		el.dispatchEvent(new Event('input', { bubbles: true }));
		el.focus();
		ElMessage.success(t('已插入: ') + refText);
	} else {
		// 兜底：复制到剪贴板
		navigator.clipboard.writeText(refText).then(() => {
			ElMessage.success(t('已复制: ') + refText);
		}).catch(() => {
			ElMessage.info(t('变量引用: ') + refText);
		});
	}
}
</script>

<style lang="scss" scoped>
.config-panel {
	width: 360px;
	background-color: #fff;
	border-left: 1px solid var(--el-border-color-light);
	display: flex;
	flex-direction: column;
	z-index: 5;

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px;
		border-bottom: 1px solid var(--el-border-color-light);

		&__title {
			font-size: 15px;
			font-weight: 600;
		}
	}

	.panel-content {
		flex: 1;
		padding: 16px;
	}
}

.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.variable-ref-panel {
	margin-bottom: 12px;
	padding: 10px;
	background: var(--el-fill-color-light);
	border-radius: 6px;
	border: 1px solid var(--el-border-color-lighter);
}

.variable-section {
		margin-bottom: 8px;
	}

	.variable-section-title {
		font-size: 11px;
		font-weight: 600;
		color: var(--el-text-color-secondary);
		margin-bottom: 6px;
		padding-left: 2px;
	}

	.variable-tag--loop {
		background: rgba(230, 162, 60, 0.1) !important;
		border-color: rgba(230, 162, 60, 0.3) !important;
		color: var(--el-color-warning) !important;
	}

	.variable-ref-title {
	font-size: 12px;
	font-weight: 600;
	color: var(--el-text-color-secondary);
	margin-bottom: 8px;
}

.variable-ref-list {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
}

.variable-tag {
	cursor: pointer;
	transition: all 0.2s;

	&:hover {
		color: var(--el-color-primary);
		border-color: var(--el-color-primary);
	}
}

.variable-source {
	margin-left: 4px;
	font-size: 10px;
	opacity: 0.6;
}

.variable-ref-hint {
	margin-top: 8px;
	padding-top: 8px;
	border-top: 1px dashed var(--el-border-color-lighter);

	.hint-item {
		font-size: 11px;
		color: var(--el-text-color-placeholder);
		margin-bottom: 2px;

		.hint-label {
			font-weight: 500;
		}

		code {
			background: var(--el-fill-color);
			padding: 1px 4px;
			border-radius: 3px;
			font-size: 11px;
		}
	}
}
</style>
