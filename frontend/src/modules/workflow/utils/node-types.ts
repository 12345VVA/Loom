import type { Component } from 'vue';

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
 * 注册自定义节点组件（key 与后端编译器的节点 type 一一对应）。
 * deprecated `tool` 已下架（三期B7 / WF-P2-10）：后端加载入口自动迁移为
 * tool_executor，画布不再渲染该类型。
 */
export const nodeTypes: Record<string, Component> = {
	start: StartNode,
	end: EndNode,
	llm: LlmNode,
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

/**
 * 注册自定义边组件
 */
export const edgeTypes: Record<string, Component> = { label: LabelEdge };
