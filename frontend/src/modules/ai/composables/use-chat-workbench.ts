import { computed, nextTick, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { useStream } from '/@/cool/service/stream';
import { aiRuntime } from '/$/ai';
import {
	CHAT_IMAGE_MAX_COUNT,
	buildMessageContent,
	readFileAsDataUri,
	supportsVision,
	validateImageFile
} from '../utils/chat-images';

export interface ChatMessageItem {
	id: number;
	role: 'user' | 'assistant';
	content: string;
	/** 用户消息附带图片（data URI，仅内存态不落库） */
	images?: string[];
	time?: string;
}

export interface ChatProfileOption {
	label: string;
	value: string;
	/** 模型 capabilities 解析结果：true=支持视觉；false=明确不支持；null=未配置（放行） */
	supportsVision: boolean | null;
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

	const profileOptions = ref<ChatProfileOption[]>([]);
	const prompt = ref('');
	const pendingImages = ref<string[]>([]);
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
				value: item.code,
				supportsVision: supportsVision(item.modelCapabilities)
			}));

			if (!form.profileCode && profileOptions.value.length) {
				const def = profileOptions.value.find(p => p.value.includes('default') || p.value.includes('chat'));
				form.profileCode = def ? def.value : profileOptions.value[0].value;
			}
		} catch (e: any) {
			console.error('加载模型 Profile 失败', e);
		}
	}

	/** 当前选中 profile 的视觉能力：true 可用；false 明确不支持（隐藏入口）；null 未配置（放行） */
	const currentSupportsVision = computed<boolean | null>(() => {
		const hit = profileOptions.value.find(p => p.value === form.profileCode);
		return hit ? hit.supportsVision : null;
	});

	const canAttachImages = computed(() => currentSupportsVision.value !== false);

	async function addImageFiles(files: File[] | FileList | null) {
		if (!files || !files.length) return;
		const list = Array.from(files);
		for (const file of list) {
			if (pendingImages.value.length >= CHAT_IMAGE_MAX_COUNT) {
				ElMessage.warning(t('单条消息最多 {n} 张图片', { n: CHAT_IMAGE_MAX_COUNT }));
				return;
			}
			const err = validateImageFile(file);
			if (err) {
				ElMessage.warning(t(err));
				continue;
			}
			try {
				const dataUri = await readFileAsDataUri(file);
				pendingImages.value.push(dataUri);
			} catch {
				ElMessage.error(t('图片读取失败'));
			}
		}
	}

	function removeImage(idx: number) {
		pendingImages.value.splice(idx, 1);
	}

	function buildContextMessages(currentPromptText: string, currentImages?: string[]): any[] {
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
				if (m.content || m.images?.length) {
					// 多模态上下文：历史用户消息的图片一并携带（IR parts）；assistant 恒纯文本
					contextList.push({
						role: m.role,
						content: m.role === 'user' ? buildMessageContent(m.content, m.images) : m.content
					});
				}
			}
		}

		contextList.push({
			role: 'user',
			content: buildMessageContent(currentPromptText, currentImages)
		});

		return contextList;
	}

	async function sendChat() {
		const text = prompt.value.trim();
		const images = [...pendingImages.value];
		if (!text && !images.length) {
			ElMessage.warning(t('请输入提问内容'));
			return;
		}
		if (isBusy.value) return;

		const userMsgId = Date.now();
		messages.value.push({
			id: userMsgId,
			role: 'user',
			content: text,
			images: images.length ? images : undefined,
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
		pendingImages.value = [];
		loading.chat = true;
		scrollToBottom();

		try {
			const ctxMessages = buildContextMessages(text, images);
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
		const images = [...pendingImages.value];
		if (!text && !images.length) {
			ElMessage.warning(t('请输入提问内容'));
			return;
		}
		if (isBusy.value) return;

		const userMsgId = Date.now();
		messages.value.push({
			id: userMsgId,
			role: 'user',
			content: text,
			images: images.length ? images : undefined,
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
		pendingImages.value = [];
		loading.stream = true;
		currentStreamingId.value = assistantMsgId;
		streamStatus.value = 'connecting';
		streamEvents.value = [];
		streamCancelled = false;
		scrollToBottom();

		const ctxMessages = buildContextMessages(text, images);
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
		let prevUserImages: string[] = [];
		for (let i = targetIdx - 1; i >= 0; i--) {
			if (messages.value[i].role === 'user') {
				prevUserMsg = messages.value[i].content;
				prevUserImages = messages.value[i].images || [];
				break;
			}
		}

		if (!prevUserMsg && !prevUserImages.length) {
			ElMessage.warning(t('未找到上一条用户提问'));
			return;
		}

		messages.value.splice(targetIdx);
		prompt.value = prevUserMsg;
		pendingImages.value = [...prevUserImages];
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
		pendingImages,
		messagesContainer,
		messages,
		streamEvents,
		streamStatus,
		streamStatusType,
		showStreamDrawer,
		loading,
		isBusy,
		form,
		currentSupportsVision,
		canAttachImages,
		currentStreamingId,
		isStreamingCurrent,
		scrollToBottom,
		initProfiles,
		addImageFiles,
		removeImage,
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
