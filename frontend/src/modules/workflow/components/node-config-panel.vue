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

				<!-- 上游变量引用提示 -->
				<div v-if="upstreamVariables.length > 0" class="variable-ref-panel">
					<div class="variable-ref-title">{{ $t('上游可用变量') }}</div>
					<div class="variable-ref-list">
						<el-tag
							v-for="v in upstreamVariables"
							:key="v.nodeId + '_' + v.variableName"
							size="small"
							effect="plain"
							class="variable-tag"
							@click="insertVariableToField(v.variableName)"
						>
							{{ '{' + v.variableName + '}' }}
							<span class="variable-source">{{ v.nodeLabel }}</span>
						</el-tag>
					</div>
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
					v-model="selectedNode.data.config"
					:profiles="filteredProfiles"
					:available-target-nodes="availableTargetNodes"
				/>
			</el-form>
		</el-scrollbar>
	</div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
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

const { t } = useI18n();

const props = defineProps<{
	selectedNode: any;
	upstreamVariables: any[];
	variableSyntaxHints: any[];
	availableTargetNodes: any[];
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
	tool_executor: ToolExecutorConfig
};

// 节点类型 → 所需的 AI 模型类型映射
const NODE_MODEL_TYPE_MAP: Record<string, string> = {
	llm: 'chat',
	intent_classifier: 'chat',
	batch_processor: 'chat',
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

// 记录配置面板内最后获得焦点的输入框/文本域
const lastFocusedInput = ref<HTMLTextAreaElement | HTMLInputElement | null>(null);

function onConfigPanelFocusIn(event: FocusEvent) {
	const target = event.target;
	if (target instanceof HTMLTextAreaElement || (target instanceof HTMLInputElement && target.type === 'text')) {
		lastFocusedInput.value = target as any;
	}
}

function getVariableRefText(varName: string): string {
	const nodeType = props.selectedNode?.type;
	if (nodeType === 'condition' || nodeType === 'tool_executor') {
		return `variables.${varName}`;
	}
	return `{${varName}}`;
}

function insertVariableToField(varName: string) {
	const refText = getVariableRefText(varName);
	const el = lastFocusedInput.value;
	if (el && document.body.contains(el)) {
		const start = el.selectionStart ?? el.value.length;
		const end = el.selectionEnd ?? el.value.length;
		el.setRangeText(refText, start, end, 'end');
		el.dispatchEvent(new Event('input', { bubbles: true }));
		el.focus();
		ElMessage.success(t('已插入: ') + refText);
	} else {
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
	width: 320px;
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
