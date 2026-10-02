import { computed, nextTick, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { useStream } from '/@/cool/service/stream';
import { aiRuntime } from '/$/ai';

export interface ChatMessageItem {
	id: number;
	role: 'user' | 'assistant';
	content: string;
	time?: string;
}

export interface ChatFormState {
	profileCode: string;
	scenario: string;
	maxTokens: number;
	temperature: number;
	systemPrompt: string;
	carryContext: boolean;
}

export function useChatWorkbench() {
	const { service } = useCool();
	const { t } = useI18n();
	const stream = useStream();

	const profileOptions = ref<{ label: string; value: string }[]>([]);
	const prompt = ref('');
	const messagesContainer = ref<HTMLElement | null>(null);

	const messages = ref<ChatMessageItem[]>([]);
	const streamEvents = ref<any[]>([]);
	const streamStatus = ref('');
	const showStreamDrawer = ref(false);

	let streamCancelled = false;

	const loading = reactive({
		chat: false,
		stream: false
	});

	const isBusy = computed(() => loading.chat || loading.stream);

	const form = reactive<ChatFormState>({
		profileCode: '',
		scenario: 'default',
		maxTokens: 1024,
		temperature: 0.7,
		systemPrompt: '',
		carryContext: true
	});

	const currentStreamingId = ref<number | null>(null);

	function isStreamingCurrent(id: number): boolean {
		return loading.stream && currentStreamingId.value === id;
	}

	const streamStatusType = computed(() => {
		if (loading.stream) return 'primary';
		if (streamStatus.value.includes('done') || streamStatus.value.includes('完成')) return 'success';
		if (streamStatus.value.includes('error') || streamStatus.value.includes('失败')) return 'danger';
		return 'info';
	});

	function scrollToBottom(smooth = true) {
		nextTick(() => {
			if (messagesContainer.value) {
				messagesContainer.value.scrollTo({
					top: messagesContainer.value.scrollHeight,
					behavior: smooth ? 'smooth' : 'auto'
				});
			}
		});
	}

	function formatTime(date = new Date()): string {
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
	}

	async function initProfiles() {
		try {
			const res = await service.ai.profile.list({
				modelType: 'chat',
				status: true
			} as any);
			const list = Array.isArray(res) ? res : [];
			profileOptions.value = list.map((item: any) => ({
				label: `${item.name || item.code} / ${item.modelName || item.modelId || ''}`,
				value: item.code
			}));

			if (!form.profileCode && profileOptions.value.length) {
				const def = profileOptions.value.find(p => p.value.includes('default') || p.value.includes('chat'));
				form.profileCode = def ? def.value : profileOptions.value[0].value;
			}
		} catch (e: any) {
			console.error('加载模型 Profile 失败', e);
		}
	}

	function buildContextMessages(currentPromptText: string): any[] {
		const contextList: any[] = [];
		if (form.systemPrompt && form.systemPrompt.trim()) {
			contextList.push({
				role: 'system',
				content: form.systemPrompt.trim()
			});
		}

		if (form.carryContext) {
			const history = messages.value.slice(-10);
			for (const m of history) {
				if (m.content) {
					contextList.push({
						role: m.role,
						content: m.content
					});
				}
			}
		}

		contextList.push({
			role: 'user',
			content: currentPromptText
		});

		return contextList;
	}

	async function sendChat() {
		const text = prompt.value.trim();
		if (!text) {
			ElMessage.warning(t('请输入提问内容'));
			return;
		}
		if (isBusy.value) return;

		const userMsgId = Date.now();
		messages.value.push({
			id: userMsgId,
			role: 'user',
			content: text,
			time: formatTime()
		});

		const assistantMsgId = userMsgId + 1;
		const assistantMsg: ChatMessageItem = {
			id: assistantMsgId,
			role: 'assistant',
			content: '',
			time: formatTime()
		};
		messages.value.push(assistantMsg);

		prompt.value = '';
		loading.chat = true;
		scrollToBottom();

		try {
			const ctxMessages = buildContextMessages(text);
			const payload: any = {
				messages: ctxMessages,
				scenario: form.scenario || 'default',
				temperature: form.temperature,
				maxTokens: form.maxTokens
			};
			if (form.profileCode) {
				payload.profileCode = form.profileCode;
			}

			const res = await aiRuntime.chat(payload);
			assistantMsg.content = res.content || (typeof res === 'string' ? res : JSON.stringify(res));
			assistantMsg.time = formatTime();
		} catch (e: any) {
			assistantMsg.content = `[${t('调用失败')}]: ${e?.message || t('未知网络异常')}`;
			assistantMsg.time = formatTime();
			ElMessage.error(assistantMsg.content);
		} finally {
			loading.chat = false;
			scrollToBottom();
		}
	}

	async function sendStream() {
		const text = prompt.value.trim();
		if (!text) {
			ElMessage.warning(t('请输入提问内容'));
			return;
		}
		if (isBusy.value) return;

		const userMsgId = Date.now();
		messages.value.push({
			id: userMsgId,
			role: 'user',
			content: text,
			time: formatTime()
		});

		const assistantMsgId = userMsgId + 1;
		const assistantMsg: ChatMessageItem = {
			id: assistantMsgId,
			role: 'assistant',
			content: '',
			time: formatTime()
		};
		messages.value.push(assistantMsg);

		prompt.value = '';
		loading.stream = true;
		currentStreamingId.value = assistantMsgId;
		streamStatus.value = 'connecting';
		streamEvents.value = [];
		streamCancelled = false;
		scrollToBottom();

		const ctxMessages = buildContextMessages(text);
		const payload: any = {
			messages: ctxMessages,
			scenario: form.scenario || 'default',
			temperature: form.temperature,
			maxTokens: form.maxTokens
		};
		if (form.profileCode) {
			payload.profileCode = form.profileCode;
		}

		let content = '';

		try {
			await stream.invoke({
				url: aiRuntime.streamUrl(),
				data: payload,
				cb(event: any) {
					streamEvents.value.push(event);
					streamStatus.value = event.event || 'message';

					if (event.event === 'delta') {
						content += event.content || '';
						assistantMsg.content = content;
						scrollToBottom(false);
					}

					if (event.event === 'done') {
						if (!content && event.content) {
							content = event.content;
							assistantMsg.content = content;
						}
						loading.stream = false;
						currentStreamingId.value = null;
						assistantMsg.time = formatTime();
					}

					if (event.event === 'error') {
						if (streamCancelled) return;
						ElMessage.error(event.message || t('流式交互失败'));
						if (!content) {
							removeMessage(assistantMsg.id);
						}
						loading.stream = false;
						currentStreamingId.value = null;
						assistantMsg.time = formatTime();
					}
				}
			});
		} catch (err: any) {
			if (err.name !== 'AbortError' && !streamCancelled) {
				ElMessage.error(err.message || t('流式连接失败'));
				assistantMsg.content = `[${t('流式连接失败')}]: ${err?.message || t('未知网络异常')}`;
			}
			loading.stream = false;
			currentStreamingId.value = null;
			assistantMsg.time = formatTime();
		}
	}

	function stopStream() {
		try {
			streamCancelled = true;
			stream.cancel();
			streamStatus.value = 'cancelled';
			loading.stream = false;
			currentStreamingId.value = null;
			ElMessage.info(t('已中止生成'));
		} catch (e) {
			console.error('中止流失败', e);
		}
	}

	function removeMessage(id: number) {
		const idx = messages.value.findIndex(m => m.id === id);
		if (idx !== -1) {
			messages.value.splice(idx, 1);
		}
	}

	function regenerateFrom(id: number) {
		const targetIdx = messages.value.findIndex(m => m.id === id);
		if (targetIdx === -1) return;

		let prevUserMsg = '';
		for (let i = targetIdx - 1; i >= 0; i--) {
			if (messages.value[i].role === 'user') {
				prevUserMsg = messages.value[i].content;
				break;
			}
		}

		if (!prevUserMsg) {
			ElMessage.warning(t('未找到上一条用户提问'));
			return;
		}

		messages.value.splice(targetIdx);
		prompt.value = prevUserMsg;
		sendStream();
	}

	function clearMessages() {
		messages.value = [];
		streamEvents.value = [];
		streamStatus.value = '';
	}

	function clearStreamLogs() {
		streamEvents.value = [];
	}

	async function copyStreamLogs() {
		try {
			const str = JSON.stringify(streamEvents.value, null, 2);
			await navigator.clipboard.writeText(str);
			ElMessage.success(t('已复制所有实时事件'));
		} catch {
			ElMessage.warning(t('复制失败'));
		}
	}

	return {
		profileOptions,
		prompt,
		messagesContainer,
		messages,
		streamEvents,
		streamStatus,
		streamStatusType,
		showStreamDrawer,
		loading,
		isBusy,
		form,
		currentStreamingId,
		isStreamingCurrent,
		scrollToBottom,
		initProfiles,
		sendChat,
		sendStream,
		stopStream,
		removeMessage,
		regenerateFrom,
		clearMessages,
		clearStreamLogs,
		copyStreamLogs
	};
}
