import type { InjectionKey, Ref } from 'vue';

export const UPSTREAM_VARIABLES_KEY = 'upstreamVariables' as unknown as InjectionKey<Ref<any[]>>;
export const LOOP_CONTEXT_VARS_KEY = 'loopContextVars' as unknown as InjectionKey<Ref<any[]>>;
export const UPSTREAM_OUTPUT_VARS_KEY = 'upstreamOutputVars' as unknown as InjectionKey<Ref<any[]>>;
export const VARIABLE_SYNTAX_HINTS_KEY = 'variableSyntaxHints' as unknown as InjectionKey<Ref<any[]>>;

export const UNTESTABLE_NODE_TYPES = ['start', 'end', 'loop_controller', 'batch_processor', 'human_input', 'loop_body_group'];
export const OPEN_NODE_TEST_DIALOG_KEY = 'openNodeTestDialog' as unknown as InjectionKey<(node: any) => void>;
export const SECTION_COLLAPSE_STATE_KEY = 'sectionCollapseState' as unknown as InjectionKey<Ref<Map<string, boolean>>>;
export const CONFIG_PANEL_NODE_ID_KEY = 'configPanelNodeId' as unknown as InjectionKey<Ref<string>>;
