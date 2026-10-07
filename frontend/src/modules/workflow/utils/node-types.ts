import { defineComponent, h, type Component } from 'vue';

import { isRequiredConfigMissing } from '../utils';
import LabelEdge from '../components/custom-edges/label-edge.vue';
import BatchProcessorNode from '../components/custom-nodes/batch-processor-node.vue';
import ConditionNode from '../components/custom-nodes/condition-node.vue';
import EndNode from '../components/custom-nodes/end-node.vue';
import HumanInputNode from '../components/custom-nodes/human-input-node.vue';
import ImageGeneratorNode from '../components/custom-nodes/image-generator-node.vue';
import IntentClassifierNode from '../components/custom-nodes/intent-classifier-node.vue';
import LlmNode from '../components/custom-nodes/llm-node.vue';
import LoopBodyGroupNode from '../components/custom-nodes/loop-body-group-node.vue';
import LoopControllerNode from '../components/custom-nodes/loop-controller-node.vue';
import StartNode from '../components/custom-nodes/start-node.vue';
import SwitchNode from '../components/custom-nodes/switch-node.vue';
import ToolExecutorNode from '../components/custom-nodes/tool-executor-node.vue';
import VariableAssignmentNode from '../components/custom-nodes/variable-assignment-node.vue';
import VariableTransformNode from '../components/custom-nodes/variable-transform-node.vue';

/**
 * 复审 P1-8：画布「配置不完整红点」接线——14 个 custom-node 声明并透传 incomplete
 * prop，但此前无任何生产者（死链路，红点永不出现）。此处统一按节点类型 + data.config
 * 计算 isRequiredConfigMissing 注入，custom-node 组件零改动；attrs（label/selected/
 * data/事件等 Vue Flow 下发 props）原样透传。
 */
function withIncompleteBadge(type: string, Comp: Component): Component {
	return defineComponent({
		name: `workflow-node-${type}`,
		inheritAttrs: false,
		setup(_, { attrs }) {
			return () =>
				h(Comp, {
					...attrs,
					incomplete: isRequiredConfigMissing({
						type,
						data: attrs.data as { config?: Record<string, unknown> } | undefined
					})
				});
		}
	});
}

/**
 * 注册自定义节点组件（key 与后端编译器的节点 type 一一对应）。
 * deprecated `tool` 已下架（三期B7 / WF-P2-10）：后端加载入口自动迁移为
 * tool_executor，画布不再渲染该类型。
 */
export const nodeTypes: Record<string, Component> = {
	start: withIncompleteBadge('start', StartNode),
	end: withIncompleteBadge('end', EndNode),
	llm: withIncompleteBadge('llm', LlmNode),
	condition: withIncompleteBadge('condition', ConditionNode),
	switch: withIncompleteBadge('switch', SwitchNode),
	human_input: withIncompleteBadge('human_input', HumanInputNode),
	intent_classifier: withIncompleteBadge('intent_classifier', IntentClassifierNode),
	loop_controller: withIncompleteBadge('loop_controller', LoopControllerNode),
	batch_processor: withIncompleteBadge('batch_processor', BatchProcessorNode),
	image_generator: withIncompleteBadge('image_generator', ImageGeneratorNode),
	tool_executor: withIncompleteBadge('tool_executor', ToolExecutorNode),
	loop_body_group: withIncompleteBadge('loop_body_group', LoopBodyGroupNode),
	variable_assignment: withIncompleteBadge('variable_assignment', VariableAssignmentNode),
	variable_transform: withIncompleteBadge('variable_transform', VariableTransformNode)
};

/**
 * 注册自定义边组件
 */
export const edgeTypes: Record<string, Component> = { label: LabelEdge };
