/**
 * 各节点类型的默认 config 构建规则（从 editor.vue handleAddNode 抽出）。
 *
 * 静态部分放 `base`；`outputVariable` 类字段依赖节点 label 做全局去重，
 * 由 `buildDefaultConfig` 在调用时动态生成，故仅在此声明默认名与写入字段名。
 */
export interface DefaultConfigSpec {
	/** 静态 config 字段（不含动态生成的 outputVariable） */
	base: Record<string, any>;
	/** 若该类型需要 outputVariable，指定其默认名（如 'output'），构建时按 label 拼前缀并去重 */
	outputVarDefault?: string;
	/** outputVariable 写入的字段名；绝大多数为 'outputVariable'，仅 variable_transform 用 'output_variable' */
	outputVarKey?: string;
}

export const NODE_DEFAULT_CONFIGS: Record<string, DefaultConfigSpec> = {
	llm: {
		base: {
			modelProfileCode: '',
			systemPromptTemplate: '',
			promptTemplate: '',
			outputFormat: 'text',
			jsonFields: []
		},
		outputVarDefault: 'output'
	},
	condition: { base: { expression: '', trueRoute: '', falseRoute: '' } },
	switch: { base: { variable: '', cases: [], defaultRoute: '' } },
	human_input: { base: { message: '' }, outputVarDefault: 'approval_status' },
	intent_classifier: { base: { modelProfileCode: '', intents: [], defaultRoute: '' } },
	loop_controller: {
		base: {
			listVariable: 'list_variable',
			itemVariable: 'loop_item',
			loopBodyRoute: '',
			exitRoute: ''
		},
		outputVarDefault: 'loop_results'
	},
	batch_processor: {
		base: {
			batchListVariable: 'batch_list_variable',
			itemVariable: 'batch_item',
			concurrencyLimit: 5,
			loopBodyRoute: '',
			exitRoute: ''
		},
		outputVarDefault: 'batch_results'
	},
	image_generator: {
		base: {
			modelProfileCode: '',
			promptTemplate: '',
			size: '',
			imageVariable: '',
			imageTemplate: '',
			optionsJson: '{}'
		},
		outputVarDefault: 'image_url'
	},
	tool_executor: {
		base: { toolCode: '', argumentsJson: '{}' },
		outputVarDefault: 'tool_result'
	},
	variable_assignment: { base: { assignments: [] } },
	variable_transform: {
		base: {
			input_variable: '',
			transform_type: 'join_array',
			transform_args: {}
		},
		outputVarDefault: 'transformed_value',
		outputVarKey: 'output_variable'
	},
	end: { base: { outputFormat: 'json', outputFields: [] } }
};

/**
 * 构建指定类型的默认 config。
 * 深拷贝 `base`（避免数组/对象字段跨节点共享引用），并按需注入唯一 outputVariable。
 *
 * @param type 节点类型
 * @param label 节点标签（用作 outputVariable 前缀）
 * @param uniqueVar 给定 (label, defaultVar) 返回去重后的变量名
 */
export function buildDefaultConfig(
	type: string,
	label: string,
	uniqueVar: (label: string, defaultVar: string) => string
): Record<string, any> {
	const spec = NODE_DEFAULT_CONFIGS[type];
	// JSON 深拷贝：base 含 cases/jsonFields 等数组/对象，必须每节点独立
	const config: Record<string, any> = spec ? JSON.parse(JSON.stringify(spec.base)) : {};
	if (spec?.outputVarDefault) {
		const key = spec.outputVarKey || 'outputVariable';
		config[key] = uniqueVar(label, spec.outputVarDefault);
	}
	return config;
}
