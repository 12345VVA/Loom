import type { InjectionKey, Ref } from 'vue';

export const UPSTREAM_VARIABLES_KEY = 'upstreamVariables' as unknown as InjectionKey<Ref<any[]>>;
export const LOOP_CONTEXT_VARS_KEY = 'loopContextVars' as unknown as InjectionKey<Ref<any[]>>;
export const UPSTREAM_OUTPUT_VARS_KEY = 'upstreamOutputVars' as unknown as InjectionKey<Ref<any[]>>;
export const VARIABLE_SYNTAX_HINTS_KEY = 'variableSyntaxHints' as unknown as InjectionKey<
	Ref<any[]>
>;

// 不可单节点测试的节点类型 / mock 占位工具集合：由后端生成的节点元数据 manifest
// 派生（三期B7 / WF-P2-7 单一来源化）。权威来源 backend 的注册表与 graph_validate
// 常量集；跨栈守卫 backend/tests/test_workflow_untestable_sync.py 比对生成产物。
// 再生成：cd backend && python scripts/dump_node_manifest.py
export { UNTESTABLE_NODE_TYPES, MOCK_TOOL_CODES } from '../generated/node-manifest';
export const OPEN_NODE_TEST_DIALOG_KEY = 'openNodeTestDialog' as unknown as InjectionKey<
	(node: any) => void
>;
export const SECTION_COLLAPSE_STATE_KEY = 'sectionCollapseState' as unknown as InjectionKey<
	Ref<Map<string, boolean>>
>;
export const CONFIG_PANEL_NODE_ID_KEY = 'configPanelNodeId' as unknown as InjectionKey<Ref<string>>;
