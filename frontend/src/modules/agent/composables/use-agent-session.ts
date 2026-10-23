import { computed, ref } from 'vue';
import { useCool, useStream } from '/@/cool';

export type RunEventType =
	| 'run_started'
	| 'model_started'
	| 'model_finished'
	| 'tool_started'
	| 'tool_finished'
	| 'tool_skipped'
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

/** 本地进行中的工具调用块（SSE 事件驱动渲染） */
export interface LiveToolBlock {
	toolCallId: string;
	toolName: string;
	status: 'running' | 'done' | 'skipped';
}

const TERMINAL_EVENTS: RunEventType[] = ['final', 'error', 'cancelled', 'timed_out'];

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

	const currentProfileId = ref<number | undefined>(undefined);
	const publishedProfiles = computed(() => profiles.value.filter((p) => p.status === 'published'));

	// 流式过程中累积的 assistant 文本（final 后由服务端消息刷新替代）
	const streamingText = ref('');

	async function loadProfiles() {
		profiles.value = await service.agent.profile.list();
		if (!currentProfileId.value) {
			const first = mode === 'published' ? publishedProfiles.value[0] : profiles.value[0];
			currentProfileId.value = first?.id ?? null;
		}
	}

	async function loadSessions() {
		// EPS 实体类型为全可选+失真形态（asset 期坑⑩）——行模型收敛走运行时过滤，此处断言放宽
		sessions.value = ((await service.agent.session.list({ page: 1, size: 100 })) ||
			[]) as unknown as AgentSessionRow[];
	}

	async function openSession(row: AgentSessionRow) {
		currentSessionId.value = row.id;
		currentProfileId.value = row.profileId;
		messages.value = ((await service.agent.session.messages({ session_id: row.id })) || []) as any[];
	}

	function newSession() {
		currentSessionId.value = null;
		messages.value = [];
		streamingText.value = '';
	}

	/** 发送一条消息（SSE）。终态后重拉服务端消息（权威口径）。 */
	async function send(question: string) {
		if (running.value || !question.trim() || !currentProfileId.value) return;
		running.value = true;
		stopHint.value = '';
		streamingText.value = '';
		messages.value.push({ role: 'user', content: question });

		try {
			const url = mode === 'published' ? '/admin/agent/chat/chatStream' : '/admin/agent/profile/debugChat';
			await stream.invoke({
				url,
				method: 'POST',
				data: {
					profileId: currentProfileId.value,
					sessionId: currentSessionId.value,
					question
				},
				cb: (event: RunEvent) => {
					handleEvent(event);
				}
			});
		} catch (err: any) {
			stopHint.value = err?.message || '连接中断';
		} finally {
			await refreshAfterRun();
			running.value = false;
			runningTool.value = null;
			traceToken.value = null;
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
			case 'tool_started':
				runningTool.value = {
					toolCallId: event.payload?.toolCallId,
					toolName: event.payload?.toolName,
					status: 'running'
				};
				break;
			case 'tool_finished':
			case 'tool_skipped':
				if (runningTool.value && runningTool.value.toolCallId === event.payload?.toolCallId) {
					runningTool.value = {
						...runningTool.value,
						status: event.type === 'tool_finished' ? 'done' : 'skipped'
					};
				}
				break;
			case 'model_finished':
				// 轮次粒度（一期不做 token 级流式）：文本在终态后整体刷新
				break;
			case 'final':
				streamingText.value = event.payload?.answer || '';
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
				[]) as any[];
		} catch {
			// draft 会话 messages 走同一端点；失败时保留流式文本兜底
		}
		streamingText.value = '';
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
		traceToken,
		stopHint,
		streamingText,
		loadProfiles,
		loadSessions,
		openSession,
		newSession,
		send,
		stop
	};
}
