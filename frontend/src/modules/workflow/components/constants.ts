import type { InjectionKey, Ref } from 'vue';

export const UPSTREAM_VARIABLES_KEY = 'upstreamVariables' as unknown as InjectionKey<Ref<any[]>>;
export const LOOP_CONTEXT_VARS_KEY = 'loopContextVars' as unknown as InjectionKey<Ref<any[]>>;
export const UPSTREAM_OUTPUT_VARS_KEY = 'upstreamOutputVars' as unknown as InjectionKey<Ref<any[]>>;
export const VARIABLE_SYNTAX_HINTS_KEY = 'variableSyntaxHints' as unknown as InjectionKey<
	Ref<any[]>
>;

// 不可单节点测试的节点类型。⚠️ 权威来源是后端
// backend/app/modules/workflow/service/graph_validate.py 的 UNTESTABLE_NODE_TYPES，
// 两处需保持一致（后端 /testNode 400 兜底拦截；改动任一侧必须同步另一侧）。
export const UNTESTABLE_NODE_TYPES = [
	'start',
	'end',
	'loop_controller',
	'batch_processor',
	'human_input',
	'loop_body_group'
];
export const OPEN_NODE_TEST_DIALOG_KEY = 'openNodeTestDialog' as unknown as InjectionKey<
	(node: any) => void
>;
export const SECTION_COLLAPSE_STATE_KEY = 'sectionCollapseState' as unknown as InjectionKey<
	Ref<Map<string, boolean>>
>;
export const CONFIG_PANEL_NODE_ID_KEY = 'configPanelNodeId' as unknown as InjectionKey<Ref<string>>;
