// 智能体模块对外 API 出口（module.mdc：跨模块引用一律走 /$/agent）。
// 会话/调试台共享逻辑在 ./composables/use-agent-session（模块内使用，不对外导出）。
export { default as ChatMessage } from './components/chat-message.vue';
export { default as ToolTracePanel } from './components/tool-trace-panel.vue';
