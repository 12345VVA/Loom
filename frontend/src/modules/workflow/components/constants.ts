import type { InjectionKey, Ref } from 'vue';

export const UPSTREAM_VARIABLES_KEY = 'upstreamVariables' as unknown as InjectionKey<Ref<any[]>>;
export const LOOP_CONTEXT_VARS_KEY = 'loopContextVars' as unknown as InjectionKey<Ref<any[]>>;
export const UPSTREAM_OUTPUT_VARS_KEY = 'upstreamOutputVars' as unknown as InjectionKey<Ref<any[]>>;
export const VARIABLE_SYNTAX_HINTS_KEY = 'variableSyntaxHints' as unknown as InjectionKey<Ref<any[]>>;
