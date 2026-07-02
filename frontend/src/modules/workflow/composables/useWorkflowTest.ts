import { reactive, ref, type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import { findInvalidNodeInput } from '../utils';
import { useStream } from '/@/cool/service/stream';
import dayjs from 'dayjs';

import type { FlowNode } from '../types/editor';

// 实例终态：收到这些状态后停止 SSE 流
const TERMINAL_STATUSES = new Set(['success', 'failed', 'paused', 'cancelled']);
// 节点完成事件触发 logs 刷新的防抖间隔（合并快速工作流的连续事件）
const LOG_REFRESH_DEBOUNCE_MS = 300;
// SSE 异常断开后的最大重连次数
const MAX_RECONNECT_ATTEMPTS = 10;

export function useWorkflowTest(
	service: any,
	t: any,
	workflowId: Ref<string | null>,
	isDirty: Ref<boolean>,
	elements: Ref<any[]>,
	saveWorkflow: () => Promise<boolean | undefined>
) {
	// 测试弹窗
	const testDialog = reactive({
		visible: false,
		loading: false,
		form: {
			inputsJson: '{}'
		}
	});

	// 测试运行日志抽屉
	const testLogDrawer = reactive({
		visible: false,
		loading: false,
		instanceId: null as number | null,
		status: '',
		items: [] as any[]
	});

	// SSE 实时流（替代原定时轮询）
	const stream = useStream();
	let streamActive = false;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let logRefreshTimer: ReturnType<typeof setTimeout> | null = null;
	let reconnectAttempts = 0;

	function clearTestStatus() {
		stopStream();
		testLogDrawer.instanceId = null;
		testLogDrawer.visible = false;
		testLogDrawer.items = [];
		testLogDrawer.status = '';
		clearNodeStatus();
	}

	function reopenTestLogDrawer() {
		if (testLogDrawer.instanceId) {
			testLogDrawer.visible = true;
			// 重开抽屉时，若实例仍在运行且 SSE 已断开，重连续接
			if (!streamActive && !TERMINAL_STATUSES.has(testLogDrawer.status)) {
				startStream();
			}
		}
	}

	async function openTestDialog() {
		if (!workflowId.value) {
			ElMessage.warning(t('请先保存新建的工作流然后再进行测试。'));
			return;
		}
		if (isDirty.value) {
			const saved = await saveWorkflow();
			if (!saved) return;
		}
		// 阻断：节点 inputs 变量名非法（空/格式错/重名）时不允许提交测试
		const invalidInput = findInvalidNodeInput(elements.value);
		if (invalidInput) {
			ElMessage.warning(invalidInput.error);
			return;
		}
		const startNode = elements.value.find(
			(el: any) => !('source' in el) && el.type === 'start'
		) as FlowNode | undefined;
		if (startNode && startNode.data?.config?.inputVariables) {
			const vars: string[] = startNode.data.config.inputVariables;
			const inputs: Record<string, string> = {};
			vars.forEach(v => {
				if (v) inputs[v] = '';
			});
			testDialog.form.inputsJson = JSON.stringify(inputs, null, 2);
		} else {
			testDialog.form.inputsJson = '{}';
		}
		testDialog.visible = true;
	}

	async function startTestRun() {
		let inputs = {};
		try {
			inputs = JSON.parse(testDialog.form.inputsJson);
		} catch (e) {
			ElMessage.warning(t('初始输入变量 JSON 格式错误！'));
			return;
		}

		testDialog.loading = true;
		try {
			// 试运行走 /trial（跑草稿版）；正式运行入口 instance.vue 仍用 .start（跑已发布版）
			const res = await (service as any).workflow.instance.trial({
				definitionId: Number(workflowId.value),
				inputs
			});
			ElMessage.success(t('工作流测试实例已启动'));
			testDialog.visible = false;

			const instId = res?.id;
			if (!instId) {
				ElMessage.error(t('启动测试失败，无法获取实例ID'));
				return;
			}

			testLogDrawer.instanceId = instId;
			testLogDrawer.visible = true;
			testLogDrawer.items = [];
			testLogDrawer.status = 'running';

			clearNodeStatus();
			startStream();
		} catch (err: any) {
			ElMessage.error(t('启动测试失败: ') + (err.message || err));
		} finally {
			testDialog.loading = false;
		}
	}

	// ===== SSE 实时流：替代原 info+logs 定时轮询 =====

	async function startStream() {
		stopStream();
		streamActive = true;
		reconnectAttempts = 0;
		// 先对齐一次状态：断线/重开期间实例可能已进入终态（SSE 不会重发终态事件）
		await fetchLogsAndRefresh(null);
		// await 期间组件可能已卸载/抽屉关闭触发 stopStream（streamActive=false），复查避免遗留 SSE 连接
		if (!streamActive) return;
		if (TERMINAL_STATUSES.has(testLogDrawer.status)) {
			streamActive = false;
			return;
		}
		// 订阅 SSE：后端 /stream 推送命名事件，前端按 data.status 分流（useStream.parseSse 仅解析 data 字段）
		stream.invoke({
			url: `/admin/workflow/instance/stream?instanceId=${testLogDrawer.instanceId}`,
			method: 'GET',
			cb: handleStreamEvent
		}).catch(() => {
			// SSE 异常断开：非终态则指数退避重连
			if (streamActive && !TERMINAL_STATUSES.has(testLogDrawer.status)) {
				scheduleReconnect();
			}
		});
	}

	function stopStream() {
		streamActive = false;
		stream.cancel();
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		if (logRefreshTimer) {
			clearTimeout(logRefreshTimer);
			logRefreshTimer = null;
		}
	}

	function scheduleReconnect() {
		if (!streamActive || TERMINAL_STATUSES.has(testLogDrawer.status)) return;
		if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
			ElMessage.error(t('实时连接断开，请刷新后重试'));
			return;
		}
		reconnectAttempts++;
		const delay = Math.min(1000 * reconnectAttempts, 8000);
		reconnectTimer = setTimeout(() => startStream(), delay);
	}

	function handleStreamEvent(data: any) {
		const status = data?.status;
		if (!status) return;
		const currentNode = data.node_id || null;
		testLogDrawer.status = status;

		// 即时高亮当前推进到的节点（不等 logs 刷新，避免 ~300ms 视觉延迟）
		if (currentNode && status === 'running') {
			highlightRunningNode(currentNode);
		}
		// 节点完成/状态变化 → 防抖拉 logs 刷新画布与抽屉的详细 runLog
		scheduleLogRefresh(currentNode);

		if (TERMINAL_STATUSES.has(status)) {
			// 终态立即刷新一次 logs/节点状态：stopStream 会清掉防抖 timer，若仅依赖 scheduleLogRefresh 的防抖，
			// 快速工作流会因防抖(300ms)未触发就收到终态 → status=success 但日志为空、节点仍停在 running（画布卡住）
			fetchLogsAndRefresh(currentNode);
			stopStream();
		}
	}

	function highlightRunningNode(nodeId: string) {
		elements.value.forEach(el => {
			if (!('source' in el) && el.id === nodeId) {
				(el as any).class = 'node-status-running';
				if (!el.data) el.data = { config: {} };
				if (!el.data.runLog) el.data.runLog = { status: 'running' };
			}
		});
	}

	function scheduleLogRefresh(currentNode: string | null) {
		if (logRefreshTimer) clearTimeout(logRefreshTimer);
		logRefreshTimer = setTimeout(() => fetchLogsAndRefresh(currentNode), LOG_REFRESH_DEBOUNCE_MS);
	}

	async function fetchLogsAndRefresh(currentNode: string | null) {
		if (!testLogDrawer.instanceId) return;
		if (testLogDrawer.items.length === 0) {
			testLogDrawer.loading = true;
		}
		try {
			const infoPromise = (service as any).workflow.instance.info({
				id: testLogDrawer.instanceId
			});
			const logsPromise = (service as any).workflow.instance
				.logs({ instanceId: testLogDrawer.instanceId })
				.catch((err: any) => {
					console.warn('Fetch logs failed', err);
					return [];
				});

			const [info, logs] = await Promise.all([infoPromise, logsPromise]);
			testLogDrawer.status = info.status;

			const oldExpanded = new Set(
				testLogDrawer.items.filter(i => i.isExpanded).map(i => i.id)
			);
			testLogDrawer.items = logs.map((item: any, index: number) => ({
				...item,
				isExpanded:
					oldExpanded.has(item.id) ||
					item.status !== 'success' ||
					index === logs.length - 1
			}));

			updateNodeStatus(logs, info.status, currentNode || info.currentNode);

			if (TERMINAL_STATUSES.has(info.status)) {
				stopStream();
			}
		} catch (err) {
			console.error('Fetch logs failed', err);
		} finally {
			testLogDrawer.loading = false;
		}
	}

	function clearNodeStatus() {
		elements.value.forEach(el => {
			if (!('source' in el)) {
				(el as any).class = '';
				if (el.data) {
					delete el.data.runLog;
				}
			}
		});
	}

	function updateNodeStatus(logs: any[], instanceStatus: string, currentNode: string | null) {
		clearNodeStatus();
		const logMap = new Map(logs.map(log => [log.nodeId, log]));
		elements.value.forEach(el => {
			if (!('source' in el)) {
				let customClass = '';
				const nodeLog = logMap.get(el.id);
				if (nodeLog) {
					if (nodeLog.status === 'success') {
						customClass = 'node-status-success';
					} else if (nodeLog.status === 'error') {
						customClass = 'node-status-error';
					}
					if (!el.data) el.data = { config: {} };
					el.data.runLog = nodeLog;
				}

				if (instanceStatus === 'running' && currentNode && el.id === currentNode) {
					customClass = 'node-status-running';
					if (!el.data) el.data = { config: {} };
					if (!el.data.runLog) {
						el.data.runLog = { status: 'running' };
					}
				}

				(el as any).class = customClass;
			}
		});
	}

	function expandAllTestLogs() {
		testLogDrawer.items.forEach(i => (i.isExpanded = true));
	}
	function collapseAllTestLogs() {
		testLogDrawer.items.forEach(i => (i.isExpanded = false));
	}
	function formatTime(value: string) {
		return value ? dayjs(value).format('HH:mm:ss') : '-';
	}

	return {
		testDialog,
		testLogDrawer,
		clearTestStatus,
		reopenTestLogDrawer,
		openTestDialog,
		startTestRun,
		// 保留原导出名 stopLogPolling，editor.vue 调用方零改动；内部已切换为 SSE 流
		stopLogPolling: stopStream,
		expandAllTestLogs,
		collapseAllTestLogs,
		formatTime
	};
}
