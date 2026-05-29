<template>
	<div class="config-panel">
		<div class="panel-header">
			<div class="panel-header__title">{{ $t('参数配置') }}</div>
			<el-button link type="danger" :icon="Delete" @click="emit('delete')">
				{{ $t('删除节点') }}
			</el-button>
		</div>

		<el-scrollbar class="panel-content">

			<el-form :model="selectedNode.data" label-position="top">
				<el-form-item :label="$t('节点ID')">
					<el-input :model-value="selectedNode.id" disabled />
				</el-form-item>
				<el-form-item :label="$t('节点名称')">
					<el-input v-model="selectedNode.label" />
				</el-form-item>

				<el-divider />

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
import { computed, provide } from 'vue';
import { useI18n } from 'vue-i18n';
import { Delete } from '@element-plus/icons-vue';
import { UPSTREAM_VARIABLES_KEY, LOOP_CONTEXT_VARS_KEY, UPSTREAM_OUTPUT_VARS_KEY, VARIABLE_SYNTAX_HINTS_KEY } from './constants';

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

// 向下提供变量上下文，供底层组件直接引用（如 cl-variable-input, cl-editor-markdown）
provide(UPSTREAM_VARIABLES_KEY, flattenedVariables);
provide(LOOP_CONTEXT_VARS_KEY, loopContextVars);
provide(UPSTREAM_OUTPUT_VARS_KEY, upstreamOutputVars);
provide(VARIABLE_SYNTAX_HINTS_KEY, computed(() => props.variableSyntaxHints));

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
</style>
