/**
 * 工作流编辑器共享类型。
 *
 * 收敛 FlowNode / FlowEdge / WorkflowNodeData 的定义，供 editor.vue 及各 composable
 * （useNodeFactory / useEdgeConnect / useNodeTest / useWorkflowTest / useUpstreamVariables）
 * 统一引用，避免接口在多处重复声明导致“改一处漏多处”。
 */

/** 节点运行态数据（试运行 / 单节点测试写入，不参与拓扑序列化与 isDirty 判定） */
export interface WorkflowNodeData {
	config: Record<string, any>;
	runLog?: {
		status: 'success' | 'error' | 'running' | string;
		inputData?: any;
		outputData?: any;
		timeCost?: number;
	};
}

/** Vue Flow 画布节点 */
export interface FlowNode {
	id: string;
	type: string;
	label: string;
	position: { x: number; y: number };
	data: WorkflowNodeData;
	style?: Record<string, any>;
	parentNode?: string;
}

/** Vue Flow 画布连线 */
export interface FlowEdge {
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
