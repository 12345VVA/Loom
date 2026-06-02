import { reactive, ref, type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import dayjs from 'dayjs';

interface FlowNode {
	id: string;
	type: string;
	label: string;
	position: { x: number; y: number };
	data: {
		config: Record<string, any>;
		runLog?: any;
	};
	style?: Record<string, any>;
	parentNode?: string;
}

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

	let logPollTimer: ReturnType<typeof setInterval> | null = null;
	let logPollDelay = 2000;
	let consecutiveErrors = 0;
	const maxErrors = 10;

	function clearTestStatus() {
		stopLogPolling();
		testLogDrawer.instanceId = null;
		testLogDrawer.visible = false;
		testLogDrawer.items = [];
		testLogDrawer.status = '';
		clearNodeStatus();
	}

	function reopenTestLogDrawer() {
		if (testLogDrawer.instanceId) {
			testLogDrawer.visible = true;
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
		const startNode = elements.value.find((el: any) => !('source' in el) && el.type === 'start') as FlowNode | undefined;
		if (startNode && startNode.data?.config?.inputVariables) {
			const vars: string[] = startNode.data.config.inputVariables;
			const inputs: Record<string, string> = {};
			vars.forEach(v => {
				if (v) inputs[v] = "";
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
			const res = await (service as any).workflow.instance.start({
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
			startLogPolling();
		} catch (err: any) {
			ElMessage.error(t('启动测试失败: ') + (err.message || err));
		} finally {
			testDialog.loading = false;
		}
	}

	function startLogPolling() {
		stopLogPolling();
		logPollDelay = 2000;
		consecutiveErrors = 0;
		pollInstanceStatus();
	}

	function stopLogPolling() {
		if (logPollTimer) {
			clearTimeout(logPollTimer);
			logPollTimer = null;
		}
	}

	async function pollInstanceStatus() {
		if (!testLogDrawer.instanceId) return;
		try {
			// 如果是初次获取列表（items 为空），显示 loading
			if (testLogDrawer.items.length === 0) {
				testLogDrawer.loading = true;
			}
			
			const infoPromise = (service as any).workflow.instance.info({ id: testLogDrawer.instanceId });
			const logsPromise = (service as any).workflow.instance.logs({ instanceId: testLogDrawer.instanceId }).catch((err: any) => {
				console.warn('Fetch logs failed', err);
				return [];
			});
			
			const [info, logs] = await Promise.all([infoPromise, logsPromise]);
			testLogDrawer.status = info.status;
			
			const oldExpanded = new Set(testLogDrawer.items.filter(i => i.isExpanded).map(i => i.id));
			testLogDrawer.items = logs.map((item: any, index: number) => ({
				...item,
				isExpanded: oldExpanded.has(item.id) || item.status !== 'success' || index === logs.length - 1
			}));

			updateNodeStatus(logs, info.status, info.currentNode);

			if (info.status === 'success' || info.status === 'failed' || info.status === 'paused') {
				stopLogPolling();
			} else {
				consecutiveErrors = 0; // Reset on successful poll
				if (logPollDelay < 10000) logPollDelay += 1000;
				logPollTimer = setTimeout(pollInstanceStatus, logPollDelay);
			}
		} catch (err) {
			console.error('Poll failed', err);
			consecutiveErrors++;
			if (consecutiveErrors >= maxErrors) {
				stopLogPolling();
				testLogDrawer.loading = false;
				ElMessage.error(t('获取日志失败，请稍后重试'));
			} else {
				logPollTimer = setTimeout(pollInstanceStatus, logPollDelay);
			}
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

	function expandAllTestLogs() { testLogDrawer.items.forEach(i => i.isExpanded = true); }
	function collapseAllTestLogs() { testLogDrawer.items.forEach(i => i.isExpanded = false); }
	function formatTime(value: string) { return value ? dayjs(value).format('HH:mm:ss') : '-'; }

	return {
		testDialog,
		testLogDrawer,
		clearTestStatus,
		reopenTestLogDrawer,
		openTestDialog,
		startTestRun,
		stopLogPolling,
		expandAllTestLogs,
		collapseAllTestLogs,
		formatTime
	};
}
