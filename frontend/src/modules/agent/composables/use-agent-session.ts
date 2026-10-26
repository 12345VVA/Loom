import { computed, ref, watch } from 'vue';
import { useCool, useStream } from '/@/cool';
import { AnswerDraftBuffer } from '/$/agent/utils/answer-draft';

export type RunEventType =
	| 'run_started'
	| 'model_started'
	| 'model_finished'
	| 'tool_started'
	| 'tool_finished'
	| 'tool_skipped'
	| 'answer_delta'
	| 'answer_reset'
	| 'answer_done'
	| 'final'
	| 'error'
	| 'cancelled'
	| 'timed_out';

export interface RunEvent {
	type: RunEventType;
	payload: any;
	ts: string;
}

/** 会话行（EPS AgentSessionRead camelCase 形态） */
export interface AgentSessionRow {
	id: number;
	sessionCode: string;
	profileId: number;
	title?: string;
	runMode: string;
	lastMessageAt?: string;
	createTime?: string;
}

/** 消息附件引用（AgentMessage.meta.attachments，后端校验后落库） */
export interface AttachmentRef {
	id: number;
	name: string;
	mime: string;
	size: number;
	url: string;
}

/** 解析消息行的 meta JSON → attachments（异常吞，缺省空数组） */
function parseAttachments(meta?: string | null): AttachmentRef[] {
	if (!meta) return [];
	try {
		const parsed = JSON.parse(meta);
		return Array.isArray(parsed?.attachments) ? parsed.attachments : [];
	} catch {
		return [];
	}
}

/** DB 消息行 → 视图行（解析 meta 附件；AI/工具消息 meta 恒空） */
function toViewMessage(row: any): any {
	return { ...row, attachments: parseAttachments(row?.meta) };
}

/** 本地进行中的工具调用块（SSE 事件驱动渲染） */
/** 终态事件集（一次 run 恰一个；send 等它抵达后再收尾刷新） */
const TERMINAL_EVENT_TYPES: ReadonlySet<RunEventType> = new Set(['final', 'error', 'cancelled', 'timed_out']);

export interface LiveToolBlock {
	toolCallId: string;
	toolName: string;
	status: 'running' | 'done' | 'skipped';
}

/** 本轮 run 的工具步骤时间线（工作台「Agent 分析」面板数据源） */
export interface ToolStepItem extends LiveToolBlock {
	startTs: number;
	endTs?: number;
}

/** 本轮 run 的 token 累积（model_finished.usage 逐轮求和） */
export interface TokenStats {
	promptTokens: number;
	completionTokens: number;
	totalTokens: number;
}

/**
 * 智能体会话共享逻辑：SSE 流式对话（published 会话页 / draft 调试台共用）。
 *
 * 事件流模型：发送时本地推 user 气泡与占位 assistant 气泡；SSE 事件驱动工具块实时渲染；
 * 终态事件后以服务端消息列表为准重拉（trace/消息/事件三处口径一致）。
 */
export function useAgentSession(options: { mode: 'published' | 'draft' }) {
	const { service } = useCool();
	const stream = useStream();

	const mode = options.mode;
	const profiles = ref<any[]>([]);
	const sessions = ref<AgentSessionRow[]>([]);
	const currentSessionId = ref<number | null>(null);
	const messages = ref<any[]>([]);
	/** 进行中的 run 状态 */
	const running = ref(false);
	const runningTool = ref<LiveToolBlock | null>(null);
	const traceToken = ref<string | null>(null);
	const stopHint = ref<string>('');
	// 工作台「Agent 分析」：本轮 run 的工具步骤时间线 + token 累积 + 耗时（终态定格，下轮 send 清空）
	const toolSteps = ref<ToolStepItem[]>([]);
	const tokenStats = ref<TokenStats>({ promptTokens: 0, completionTokens: 0, totalTokens: 0 });
	const elapsedMs = ref<number | null>(null);
	const modelCallsCount = ref(0);
	const toolRoundsFinal = ref<number | null>(null);
	let runStartedAt = 0;

	const currentProfileId = ref<number | undefined>(undefined);
	const publishedProfiles = computed(() => profiles.value.filter((p) => p.status === 'published'));

	// 流式过程中累积的 assistant 文本（final 后由服务端消息刷新替代）
	const streamingText = ref('');
	// E1 token 流式草稿：generation_id 分桶（跨响应不混淆；seq 单调去重，断线重复帧不污染）
	const draft = new AnswerDraftBuffer();

	async function loadProfiles() {
		profiles.value = await service.agent.profile.list();
		if (!currentProfileId.value) {
			const first = mode === 'published' ? publishedProfiles.value[0] : profiles.value[0];
			currentProfileId.value = first?.id ?? null;
		}
	}

	async function loadSessions() {
		// EPS 实体类型为全可选+失真形态（asset 期坑⑩）——行模型收敛走运行时过滤，此处断言放宽；
		// 按当前智能体过滤（后端 page_query field_eq 已支持 profileId）
		sessions.value = ((await service.agent.session.list({
			page: 1,
			size: 100,
			profileId: currentProfileId.value
		})) || []) as unknown as AgentSessionRow[];
	}

	// 切换智能体即重拉该智能体的会话列表（draft 无会话语义，跳过）
	watch(currentProfileId, () => {
		if (mode === 'published') loadSessions();
	});

	async function openSession(row: AgentSessionRow) {
		currentSessionId.value = row.id;
		currentProfileId.value = row.profileId;
		messages.value = ((await service.agent.session.messages({ session_id: row.id })) || []).map(toViewMessage);
	}

	async function removeSession(row: AgentSessionRow) {
		await service.agent.session.delete({ ids: [row.id] });
		if (currentSessionId.value === row.id) {
			newSession();
		}
		await loadSessions();
	}

	function newSession() {
		currentSessionId.value = null;
		messages.value = [];
		streamingText.value = '';
	}

	/** 发送一条消息（SSE）。终态后重拉服务端消息（权威口径）。附件为已上传 media 引用。 */
	async function send(question: string, attachments: AttachmentRef[] = []) {
		if (running.value || !currentProfileId.value) return;
		if (!question.trim() && !attachments.length) return;
		running.value = true;
		stopHint.value = '';
		streamingText.value = '';
		draft.clear();
		toolSteps.value = [];
		tokenStats.value = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
		elapsedMs.value = null;
		modelCallsCount.value = 0;
		toolRoundsFinal.value = null;
		const sentMessages = messages.value.length;
		runStartedAt = Date.now();
		// 乐观气泡带附件（终态后 refreshAfterRun 以服务端行替换，meta 重解析）
		messages.value.push({ role: 'user', content: question, attachments });

		try {
			const url = mode === 'published' ? '/admin/agent/chat/chatStream' : '/admin/agent/profile/debugChat';
			// 终态信号：handleEvent 收到终态事件时 resolve。invoke 的 await 只等响应头
			// （流读取在其内部异步进行），若不等终态，refreshAfterRun 会在 run 完成前
			// 执行——assistant 气泡永不渲染、error 提示丢失（走查实测）。
			let resolveFinal!: () => void;
			const finalPromise = new Promise<void>(resolve => {
				resolveFinal = resolve;
			});
			let finalSettled = false;
			const settleFinal = () => {
				if (!finalSettled) {
					finalSettled = true;
					resolveFinal();
				}
			};
			await stream.invoke({
				url,
				method: 'POST',
				data: {
					profileId: currentProfileId.value,
					sessionId: currentSessionId.value,
					question,
					attachments: attachments.map(a => a.id)
				},
				cb: (event: RunEvent) => {
					handleEvent(event);
					if (TERMINAL_EVENT_TYPES.has(event.type)) settleFinal();
				}
			});
			// 等终态事件（或服务端 run 超时上限 + 余量，防终态帧丢失时永久挂起）
			const timeoutMs = (Number(profiles.value.find(p => p.id === currentProfileId.value)?.timeoutSeconds) || 60) * 1000 + 10_000;
			await Promise.race([finalPromise, sleep(timeoutMs)]);
			// 终态事件若因流断开丢失，cancel 断开本地读取
			if (!finalSettled) stream.cancel();
		} catch (err) {
			stopHint.value = (err instanceof Error ? err.message : '') || '连接中断';
		} finally {
			elapsedMs.value = Date.now() - runStartedAt;
			await refreshAfterRun();
			// 兜底（走查反馈：任何情况下发送都不能完全没有响应）：SSE 中间帧可能丢失，
			// error 事件未抵达时主动核对服务端 trace 终态，失败必显示错误
			if (!stopHint.value) {
				await ensureFailureHint(sentMessages);
			}
			running.value = false;
			runningTool.value = null;
			traceToken.value = null;
		}
	}

	function sleep(ms: number) {
		return new Promise<void>(resolve => setTimeout(resolve, ms));
	}

	/** SSE 终态事件丢失时的兜底：以服务端 trace 终态为准补显错误。 */
	async function ensureFailureHint(sentMessages: number) {
		const gotReply = messages.value.length > sentMessages + 1; // user 气泡之外还有内容（含工具块）
		if (gotReply && stopHint.value) return; // 正常回复且已有提示
		if (gotReply && !stopHint.value) return; // 正常回复，无需提示
		if (!currentProfileId.value) return;
		// EPS 行模型失真（asset 期坑⑩）——最小行类型收敛
		type TraceRow = { status?: string; error?: string | null };
		type TracePage = { list?: TraceRow[] };
		try {
			const page = (await service.agent.trace.page({
				page: 1,
				size: 1,
				profileId: currentProfileId.value
			})) as unknown as TracePage;
			const trace = (page?.list || [])[0];
			if (trace && trace.status && trace.status !== 'completed') {
				stopHint.value = trace.error || `运行失败（${trace.status}），请稍后重试`;
			} else if (!gotReply) {
				stopHint.value = '本次运行没有产生回复，请稍后重试';
			}
		} catch {
			// trace 查询失败保持静默——不覆盖已有提示
		}
	}

	function handleEvent(event: RunEvent) {
		switch (event.type) {
			case 'run_started':
				traceToken.value = event.payload?.traceToken ?? null;
				if (event.payload?.sessionId && !currentSessionId.value) {
					currentSessionId.value = event.payload.sessionId;
				}
				break;
			case 'tool_started': {
				runningTool.value = {
					toolCallId: event.payload?.toolCallId,
					toolName: event.payload?.toolName,
					status: 'running'
				};
				toolSteps.value = [
					...toolSteps.value,
					{
						toolCallId: event.payload?.toolCallId,
						toolName: event.payload?.toolName,
						status: 'running',
						startTs: Date.now()
					}
				];
				break;
			}
			case 'tool_finished':
			case 'tool_skipped': {
				const status = event.type === 'tool_finished' ? 'done' : 'skipped';
				if (runningTool.value && runningTool.value.toolCallId === event.payload?.toolCallId) {
					runningTool.value = { ...runningTool.value, status };
				}
				toolSteps.value = toolSteps.value.map(step =>
					step.toolCallId === event.payload?.toolCallId && step.status === 'running'
						? { ...step, status, endTs: Date.now() }
						: step
				);
				break;
			}
			case 'model_finished': {
				// 轮次粒度事件：usage 累积 + 调用计数（langchain openai 形态 prompt_tokens/completion_tokens）
				modelCallsCount.value += 1;
				const usage = event.payload?.usage || {};
				tokenStats.value = {
					promptTokens: tokenStats.value.promptTokens + (usage.prompt_tokens ?? 0),
					completionTokens: tokenStats.value.completionTokens + (usage.completion_tokens ?? 0),
					totalTokens: tokenStats.value.totalTokens + (usage.total_tokens ?? 0)
				};
				break;
			}
			case 'answer_delta': {
				// E1：生成中草稿区增量（generation 分桶 + seq 单调去重）
				const { generationId, delta, seq } = event.payload || {};
				draft.applyDelta(generationId, delta, seq);
				streamingText.value = draft.text;
				break;
			}
			case 'answer_reset':
				// 服务端同步撤销：该响应实为工具决策，草稿区清空（被撤销文本不入服务端消息）
				draft.reset(event.payload?.generationId ?? '');
				streamingText.value = draft.text;
				break;
			case 'answer_done':
				// 草稿定稿：保留至 final / 终态刷新以服务端消息替代
				break;
			case 'final':
				streamingText.value = event.payload?.answer || '';
				// 服务端权威口径覆盖本地计数（final payload：modelCalls/toolRounds）
				if (typeof event.payload?.modelCalls === 'number') {
					modelCallsCount.value = event.payload.modelCalls;
				}
				if (typeof event.payload?.toolRounds === 'number') {
					toolRoundsFinal.value = event.payload.toolRounds;
				}
				break;
			case 'error':
				stopHint.value = event.payload?.message || '运行失败';
				break;
			case 'cancelled':
				stopHint.value = '本次运行已取消';
				break;
			case 'timed_out':
				stopHint.value = '本次运行超时';
				break;
		}
	}

	/** 终态后以服务端消息为准（含 assistant 最终回答与 tool 消息）。 */
	async function refreshAfterRun() {
		if (!currentSessionId.value) return;
		try {
			messages.value = ((await service.agent.session.messages({ session_id: currentSessionId.value })) ||
				[]).map(toViewMessage);
		} catch {
			// draft 会话 messages 走同一端点；失败时保留流式文本兜底
		}
		// 会话可能在本次 run 中才创建（run_started 回填 sessionId）——终态必须同步刷新历史列表
		try {
			await loadSessions();
		} catch {
			// 列表刷新失败静默，不影响主回复展示
		}
		streamingText.value = '';
		draft.clear();
	}

	/** 停止运行（取消令牌置位；三层语义之一）。 */
	async function stop() {
		if (!traceToken.value) {
			stream.cancel();
			return;
		}
		try {
			await service.agent.chat.stopStream({ traceToken: traceToken.value });
		} finally {
			stream.cancel(); // 本地断流（执行侧确认终止后终态事件落库）
		}
	}

	return {
		mode,
		profiles,
		publishedProfiles,
		sessions,
		currentSessionId,
		currentProfileId,
		messages,
		running,
		runningTool,
		toolSteps,
		tokenStats,
		elapsedMs,
		modelCallsCount,
		toolRoundsFinal,
		traceToken,
		stopHint,
		streamingText,
		loadProfiles,
		loadSessions,
		openSession,
		newSession,
		removeSession,
		send,
		stop
	};
}
