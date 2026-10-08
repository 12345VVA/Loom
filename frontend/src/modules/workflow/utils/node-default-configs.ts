/**
 * 各节点类型的默认 config 构建规则（从 editor.vue handleAddNode 抽出）。
 *
 * 静态部分放 `base`；`outputVariable` 类字段依赖节点 label 做全局去重，
 * 由 `buildDefaultConfig` 在调用时动态生成。输出变量**默认名**的权威在后端
 * （node_schema.NODE_OUTPUT_VAR_DEFAULTS，经 generated/node-manifest.ts 下发，
 * 三期B7 / WF-P2-8），本文件不再手写默认名——此前 human_input 曾漂移为
 * approval_status（后端运行时真实语义是 approval_result）。
 */
import { NODE_MANIFEST } from '../generated/node-manifest';

export interface DefaultConfigSpec {
	/** 静态 config 字段（不含动态生成的 outputVariable） */
	base: Record<string, any>;
	/** outputVariable 写入的字段名；三期B7 起统一 'outputVariable'，此字段留作非默认键类型的扩展点 */
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
	},
	condition: {
		base: { expression: '', trueRoute: '', falseRoute: '', onExpressionError: 'fail' }
	},
	switch: { base: { variable: '', cases: [], defaultRoute: '' } },
	human_input: { base: { message: '' } },
	intent_classifier: { base: { modelProfileCode: '', inputVariable: '', intents: [], defaultRoute: '' } },
	loop_controller: {
		base: {
			listVariable: 'list_variable',
			itemVariable: 'loop_item',
			loopBodyRoute: '',
			exitRoute: '',
			collectKeys: [],
			persistGlobals: false
		}
	},
	batch_processor: {
		base: {
			batchListVariable: 'batch_list_variable',
			itemVariable: 'batch_item',
			concurrencyLimit: 5,
			loopBodyRoute: '',
			exitRoute: '',
			collectKeys: []
		}
	},
	image_generator: {
		base: {
			modelProfileCode: '',
			promptTemplate: '',
			size: '',
			imageVariable: '',
			imageTemplate: '',
			optionsJson: '{}'
		}
	},
	tool_executor: {
		base: { toolCode: '', argumentsJson: '{}' },
	},
	variable_assignment: { base: { assignments: [] } },
	variable_transform: {
		// 三期B7（WF-P2-9）：键名统一 camelCase（存量 snake 图由配置面板打开时迁移、
		// 后端 convert_keys_to_snake 编译期兜底，运行时零影响）
		base: {
			inputVariable: '',
			transformType: 'join_array',
			transformArgs: {}
		},
		outputVarKey: 'outputVariable'
	},
	// 长期记忆读写对（设计 docs/工作流长期记忆节点设计方案-2026-10-07.md §6）：
	// 默认值对齐后端 settings（topK 5 / threshold 0.35 / 预算 4000）；onError 两侧
	// 默认不同——store fail（记忆静默丢失最难排查）、recall degrade（降级仍可执行）
	memory_store: {
		base: {
			contentTemplate: '',
			memoryKeyTemplate: '',
			memoryType: 'fact',
			tags: [],
			embeddingProfileCode: '',
			onError: 'fail'
		}
	},
	memory_recall: {
		base: {
			memoryKeyTemplate: '',
			queryVariable: '',
			memoryTypeFilter: '',
			tagFilter: [],
			similarityThreshold: 0.35,
			topK: 5,
			maxContextChars: 4000,
			outputFormat: 'list',
			embeddingProfileCode: '',
			onError: 'degrade'
		}
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
	// 输出变量默认名从后端权威 manifest 读取（WF-P2-8：单一来源，修 human_input 漂移）
	const outputVarDefault = NODE_MANIFEST.find((n) => n.type === type)?.outputVarDefault;
	if (outputVarDefault) {
		const key = spec?.outputVarKey || 'outputVariable';
		config[key] = uniqueVar(label, outputVarDefault);
	}
	return config;
}
