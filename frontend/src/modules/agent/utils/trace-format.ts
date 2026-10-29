/**
 * 调用追踪共享格式化（列表页与详情抽屉同源）：状态/模式文案 + 语义色 + 耗时/Tokens 人性化 +
 * run 时间窗消息过滤 + 工具决策轮识别。
 */

export type TraceStatus = 'running' | 'waiting_approval' | 'completed' | 'failed' | 'cancelled' | 'timed_out';

/** trace 列表行（AgentRunTraceRead camelCase 子集；EPS 行类型失真，按需声明） */
export interface TraceRow {
	id?: number;
	agentName?: string;
	runMode?: string;
	status?: string;
	durationMs?: number | null;
	createTime?: string | null;
	promptTokens?: number | null;
	completionTokens?: number | null;
	modelCalls?: number;
	toolRounds?: number;
	toolCalls?: number;
	guardrailsVersion?: string | null;
	sessionId?: number;
	workflowInstanceId?: number | null;
	error?: string | null;
	[index: string]: unknown;
}

/** 会话消息行（AgentMessageRead camelCase 子集；role 后端恒有值；可选形态对齐 chat-message props） */
export interface TraceMessageRow {
	id?: number;
	role: string;
	content?: string;
	name?: string;
	toolCallId?: string;
	createTime?: string;
	meta?: string | null;
}

/** 工具调用明细行（AgentToolCallLogRead camelCase 子集） */
export interface ToolLogRow {
	id: number;
	toolName: string;
	success?: boolean | null;
	skippedReason?: string | null;
	durationMs?: number | null;
	createTime?: string | null;
	targetRef?: string | null;
	argsSummary?: string | null;
	resultSummary?: string | null;
	error?: string | null;
}

export interface TraceStatusItem {
	/** i18n key（消费侧经 t() 翻译） */
	label: string;
	value: TraceStatus;
	/**
	 * 显式语义色。dictColor 开启时 crud 按「数组索引」取主题色板（renderDict: e.color = style.colors[i]，
	 * 与 type 语义无关）——不显式给色会按位置染出「已完成=紫、失败=浅蓝」的错位效果。
	 */
	color: string;
}

// 语义色对齐 element-plus type 色板：running=蓝 waiting/超时=橙 completed=绿 failed=红 cancelled=灰
export const TRACE_STATUS_OPTIONS: TraceStatusItem[] = [
	{ label: 'agent.trace.statusRunning', value: 'running', color: '#409EFF' },
	{ label: 'agent.trace.statusWaitingApproval', value: 'waiting_approval', color: '#E6A23C' },
	{ label: 'agent.trace.statusCompleted', value: 'completed', color: '#67C23A' },
	{ label: 'agent.trace.statusFailed', value: 'failed', color: '#F56C6C' },
	{ label: 'agent.trace.statusCancelled', value: 'cancelled', color: '#909399' },
	{ label: 'agent.trace.statusTimedOut', value: 'timed_out', color: '#E6A23C' }
];

export const TRACE_MODE_OPTIONS = [
	{ label: 'agent.trace.modeDraft', value: 'draft' },
	{ label: 'agent.trace.modePublished', value: 'published' }
];

/** 终态集合（非终态行触发详情抽屉轮询刷新） */
export const TRACE_TERMINAL_STATUSES: ReadonlySet<string> = new Set(['completed', 'failed', 'cancelled', 'timed_out']);

export function traceStatusItem(status?: string): TraceStatusItem | undefined {
	return TRACE_STATUS_OPTIONS.find((s) => s.value === status);
}

/** 耗时人性化：<1s 毫秒、<1min 一位小数秒、其余分秒（1m04s） */
export function humanizeDuration(ms?: number | null): string {
	if (ms == null) return '-';
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
	let m = Math.floor(ms / 60_000);
	let s = Math.round((ms % 60_000) / 1000);
	if (s === 60) {
		m += 1;
		s = 0;
	}
	return `${m}m${String(s).padStart(2, '0')}s`;
}

/** Tokens「输入 / 输出」（双空 = 数据缺失占位） */
export function formatTokens(prompt?: number | null, completion?: number | null): string {
	if (prompt == null && completion == null) return '-';
	const fmt = (n?: number | null) => (n == null ? '-' : Number(n).toLocaleString('en-US'));
	return `${fmt(prompt)} / ${fmt(completion)}`;
}

export function formatDateTime(value?: string | null): string {
	if (!value) return '-';
	const d = new Date(value);
	if (isNaN(d.getTime())) return '-';
	const p = (n: number) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** run 时间窗缓冲：用户消息落库与 trace 创建的先后留余量；终态消息略晚于 duration 收口同理 */
const RUN_WINDOW_SLACK_MS = 5000;

/**
 * 消息轨迹按 run 过滤：时间窗 [创建-5s, 创建+耗时+5s]（running 无耗时则到当前）。
 * messages 按会话全量返回（session.messages 无 run 维度），此处以时间窗收敛到单次 run。
 */
export function filterRunMessages<T extends { createTime?: string | null }>(
	messages: T[],
	trace: { createTime?: string | null; durationMs?: number | null } | null
): T[] {
	if (!trace?.createTime) return messages;
	const startMs = new Date(trace.createTime).getTime();
	if (isNaN(startMs)) return messages;
	const start = startMs - RUN_WINDOW_SLACK_MS;
	const dur = Number(trace.durationMs);
	const end = Number.isFinite(dur) ? startMs + dur + RUN_WINDOW_SLACK_MS : Date.now() + RUN_WINDOW_SLACK_MS;
	return messages.filter((m) => {
		if (!m?.createTime) return false;
		const t = new Date(m.createTime).getTime();
		return !isNaN(t) && t >= start && t <= end;
	});
}

/** 助手工具决策轮：无文本但 meta.tool_calls 携带本轮调用清单（run_service A2 落库形态） */
export interface ToolCallTurnItem {
	id?: string;
	name?: string;
}

export function parseToolCallTurn(message?: { meta?: string | null } | null): ToolCallTurnItem[] {
	if (!message?.meta) return [];
	try {
		const calls = (JSON.parse(message.meta) as { tool_calls?: ToolCallTurnItem[] })?.tool_calls;
		return Array.isArray(calls) ? calls : [];
	} catch {
		return [];
	}
}

export function isToolCallTurn(message?: { role?: string; content?: string | null; meta?: string | null } | null): boolean {
	return (
		message?.role === 'assistant' && !String(message?.content || '').trim() && parseToolCallTurn(message).length > 0
	);
}
