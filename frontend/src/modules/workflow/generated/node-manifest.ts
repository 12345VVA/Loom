// 由 backend/scripts/dump_node_manifest.py 生成，勿手改。
// 再生成：cd backend && python scripts/dump_node_manifest.py
// 权威来源：node_executors 注册表（idempotent/deprecated）+ graph_validate 常量集
// + node_schema.NODE_OUTPUT_VAR_DEFAULTS（输出变量默认名，WF-P2-8）
// + node_schema.NODE_CONFIG_SCHEMA（config 必填口径，F3 单一来源——前端
// getMissingConfigFields 由此派生，防「前端 switch/面板星号/后端 schema」三处漂移）；
// 守卫：backend/tests/test_workflow_untestable_sync.py 比对产物与后端。

export interface NodeManifestConfigField {
	key: string;
	label: string;
	required: boolean;
	isList: boolean;
}

export interface NodeManifestEntry {
	type: string;
	untestable: boolean;
	interrupt: boolean;
	subgraph: boolean;
	conditional: boolean;
	idempotent: boolean;
	deprecated: boolean;
	outputVarDefault: string | null;
	configFields: readonly NodeManifestConfigField[];
}

export const NODE_MANIFEST: readonly NodeManifestEntry[] = [
	{ type: 'batch_processor', untestable: true, interrupt: false, subgraph: true, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'batch_results', configFields: [{ key: 'batchListVariable', label: '批处理列表变量', required: true, isList: false }] },
	{ type: 'condition', untestable: false, interrupt: false, subgraph: false, conditional: true, idempotent: true, deprecated: false, outputVarDefault: null, configFields: [{ key: 'expression', label: '条件表达式', required: true, isList: false }] },
	{ type: 'end', untestable: true, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: null, configFields: [] },
	{ type: 'human_input', untestable: true, interrupt: true, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'approval_result', configFields: [{ key: 'message', label: '提示消息', required: true, isList: false }] },
	{ type: 'image_generator', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'image_url', configFields: [{ key: 'promptTemplate', label: '提示词模板', required: true, isList: false }, { key: 'modelProfileCode', label: 'AI 模型', required: true, isList: false }, { key: 'characterId', label: '引用角色资产', required: false, isList: false }, { key: 'sceneId', label: '引用场景资产', required: false, isList: false }, { key: 'styleId', label: '引用风格资产', required: false, isList: false }] },
	{ type: 'intent_classifier', untestable: false, interrupt: false, subgraph: false, conditional: true, idempotent: true, deprecated: false, outputVarDefault: null, configFields: [] },
	{ type: 'llm', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'output', configFields: [{ key: 'promptTemplate', label: '提示词模板', required: true, isList: false }, { key: 'modelProfileCode', label: 'AI 模型', required: true, isList: false }] },
	{ type: 'loop_controller', untestable: true, interrupt: false, subgraph: true, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'loop_results', configFields: [{ key: 'listVariable', label: '循环列表变量', required: true, isList: false }] },
	{ type: 'memory_recall', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'memories', configFields: [] },
	{ type: 'memory_store', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: false, deprecated: false, outputVarDefault: 'memory_id', configFields: [{ key: 'contentTemplate', label: '记忆内容模板', required: true, isList: false }] },
	{ type: 'switch', untestable: false, interrupt: false, subgraph: false, conditional: true, idempotent: true, deprecated: false, outputVarDefault: null, configFields: [{ key: 'variable', label: '分支变量', required: true, isList: false }, { key: 'cases', label: '分支列表', required: true, isList: true }] },
	{ type: 'tool_executor', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'tool_result', configFields: [{ key: 'toolCode', label: '工具', required: true, isList: false }] },
	{ type: 'variable_assignment', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: null, configFields: [{ key: 'assignments', label: '赋值规则', required: true, isList: true }] },
	{ type: 'variable_transform', untestable: false, interrupt: false, subgraph: false, conditional: false, idempotent: true, deprecated: false, outputVarDefault: 'transformed_value', configFields: [{ key: 'inputVariable', label: '输入变量', required: true, isList: false }, { key: 'transformType', label: '转换类型', required: true, isList: false }] },
] as const;

export const UNTESTABLE_NODE_TYPES: readonly string[] = ['batch_processor', 'end', 'human_input', 'loop_body_group', 'loop_controller', 'start'];

export const INTERRUPT_NODE_TYPES: readonly string[] = ['human_input'];

export const SUBGRAPH_NODE_TYPES: readonly string[] = ['batch_processor', 'loop_controller'];

export const CONDITIONAL_NODE_TYPES: readonly string[] = ['condition', 'intent_classifier', 'switch'];

export const MOCK_TOOL_CODES: readonly string[] = ['file_system', 'mock_weather_api', 'web_search'];
