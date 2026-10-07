// 由 backend/scripts/dump_node_manifest.py 生成，勿手改。
// 再生成：cd backend && python scripts/dump_node_manifest.py
// 权威来源：node_executors 注册表（idempotent/deprecated）+ graph_validate 常量集
// + node_schema.NODE_OUTPUT_VAR_DEFAULTS（输出变量默认名，WF-P2-8）；
// 守卫：backend/tests/test_workflow_untestable_sync.py 比对产物与后端。

export interface NodeManifestEntry {
	type: string;
	untestable: boolean;
	interrupt: boolean;
	subgraph: boolean;
	conditional: boolean;
	idempotent: boolean;
	deprecated: boolean;
	outputVarDefault: string | null;
}

export const NODE_MANIFEST: readonly NodeManifestEntry[] = [
	{ type: 'batch_processor', untestable: true, interrupt: false, subgraph: true, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'batch_results' },
	{ type: 'condition', untestable: false, interrupt: false, subgraph: false, conditional: true, idempotent: true, deprecated: false, outputVarDefault: null },
	{ type: 'end', untestable: true, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: null },
	{ type: 'human_input', untestable: true, interrupt: true, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'approval_result' },
	{ type: 'image_generator', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'image_url' },
	{ type: 'intent_classifier', untestable: false, interrupt: false, subgraph: false, conditional: true, idempotent: true, deprecated: false, outputVarDefault: null },
	{ type: 'llm', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'output' },
	{ type: 'loop_controller', untestable: true, interrupt: false, subgraph: true, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'loop_results' },
	{ type: 'memory_store', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'memory_id' },
	{ type: 'switch', untestable: false, interrupt: false, subgraph: false, conditional: true, idempotent: true, deprecated: false, outputVarDefault: null },
	{ type: 'tool_executor', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'tool_result' },
	{ type: 'variable_assignment', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: null },
	{ type: 'variable_transform', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'transformed_value' },
] as const;

export const UNTESTABLE_NODE_TYPES: readonly string[] = ['batch_processor', 'end', 'human_input', 'loop_body_group', 'loop_controller', 'start'];

export const INTERRUPT_NODE_TYPES: readonly string[] = ['human_input'];

export const SUBGRAPH_NODE_TYPES: readonly string[] = ['batch_processor', 'loop_controller'];

export const CONDITIONAL_NODE_TYPES: readonly string[] = ['condition', 'intent_classifier', 'switch'];

export const MOCK_TOOL_CODES: readonly string[] = ['file_system', 'mock_weather_api', 'web_search'];
