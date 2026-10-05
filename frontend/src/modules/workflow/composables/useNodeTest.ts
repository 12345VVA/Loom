import { reactive, computed, ref, type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import { findInvalidNodeInput } from '../utils';
import type { FlowNode } from '../types/editor';

/** 单节点测试结果 */
interface NodeTestResult {
	status: 'success' | 'error';
	outputData: any;
	timeCost: number;
	error?: string;
	isTimeout?: boolean;
}

/** 单节点测试历史（sessionStorage，弹窗内回看/回填；P1-4 可观测性补偿） */
interface NodeTestHistoryEntry {
	time: string;
	inputsJson: string;
	outputData: any;
	timeCost: number;
	error?: string;
	status: 'success' | 'error';
}

const NODE_TEST_HISTORY_MAX = 5;

/** 单节点测试弹窗状态 */
interface NodeTestDialogState {
	visible: boolean;
	loading: boolean;
	nodeId: string;
	nodeLabel: string;
	nodeType: string;
	form: { inputsJson: string };
	result: NodeTestResult | null;
}

export function useNodeTest(
	service: Eps.Service,
	t: any,
	workflowId: Ref<string | null>,
	isDirty: Ref<boolean>,
	elements: Ref<any[]>,
	saveWorkflow: () => Promise<boolean | undefined>,
	getUpstreamVariablesForNode: (nodeId: string) => { variableName: string }[]
) {
	// 用于缓存用户在该节点输入的测试数据
	const mockVariablesCache = reactive<Record<string, string>>({});

	// 当前节点的测试历史（最近 N 次，刷新页面即清——仅会话级回看）
	const nodeTestHistory = ref<NodeTestHistoryEntry[]>([]);

	function historyKey(nodeId: string) {
		return `loom:nodeTestHistory:${workflowId.value}:${nodeId}`;
	}

	function loadHistory(nodeId: string): NodeTestHistoryEntry[] {
		try {
			return JSON.parse(sessionStorage.getItem(historyKey(nodeId)) || '[]');
		} catch {
			return [];
		}
	}

	function appendHistory(nodeId: string, entry: NodeTestHistoryEntry) {
		try {
			const list = loadHistory(nodeId);
			list.unshift(entry);
			sessionStorage.setItem(historyKey(nodeId), JSON.stringify(list.slice(0, NODE_TEST_HISTORY_MAX)));
		} catch {
			// 存储不可用/已满：历史为增强功能，静默跳过
		}
		nodeTestHistory.value = loadHistory(nodeId);
	}

	// 单节点测试弹窗状态
	const nodeTestDialog = reactive<NodeTestDialogState>({
		visible: false,
		loading: false,
		nodeId: '',
		nodeLabel: '',
		nodeType: '',
		form: {
			inputsJson: '{}'
		},
		result: null
	});

	// 并发测试隔离令牌：每次发起测试自增，过期请求（用户已切走/再次测试）的结果被丢弃
	let testToken = 0;

	/**
	 * 打开单节点测试弹窗。
	 * 会自动检查未保存修改并触发保存，确保后端读到最新配置。
	 */
	async function openNodeTestDialog(nodeId: string) {
		// 确保工作流已保存且配置为最新，避免测试过期配置
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

		const node = elements.value.find((el: any) => !('source' in el) && el.id === nodeId) as
			| FlowNode
			| undefined;
		if (!node) return;

		nodeTestDialog.nodeId = node.id;
		nodeTestDialog.nodeLabel = node.label;
		nodeTestDialog.nodeType = node.type;
		nodeTestDialog.result = null;
		nodeTestHistory.value = loadHistory(node.id);

		// 智能预填变量：优先使用缓存，其次根据上游变量推导
		if (mockVariablesCache[node.id]) {
			nodeTestDialog.form.inputsJson = mockVariablesCache[node.id];
		} else {
			const definedInputs = node.data?.config?.inputs || [];
			const inputs: Record<string, any> = {};
			definedInputs.forEach((v: any) => {
				inputs[v.name] = '';
			});
			nodeTestDialog.form.inputsJson = JSON.stringify(inputs, null, 2);
		}
		nodeTestDialog.visible = true;
	}

	/**
	 * 执行单节点测试。完成后保持弹窗打开展示结果。
	 */
	async function startNodeTest() {
		const testNodeId = nodeTestDialog.nodeId;
		if (!testNodeId) return;
		// 发起本次测试的令牌；异步返回时若已过期（用户切走或再次测试）则丢弃结果
		const token = ++testToken;

		let mockVariables = {};
		try {
			mockVariables = JSON.parse(nodeTestDialog.form.inputsJson);
			// 解析成功后缓存用户的输入，方便重复测试
			mockVariablesCache[testNodeId] = nodeTestDialog.form.inputsJson;
		} catch (e) {
			ElMessage.warning(t('初始输入变量 JSON 格式错误！'));
			return;
		}

		nodeTestDialog.loading = true;
		nodeTestDialog.result = null;
		try {
			const res = await service.workflow.instance.testNode({
				definitionId: Number(workflowId.value),
				nodeId: testNodeId,
				mockVariables
			});

			// 令牌过期：用户已切到其它节点或再次发起了测试，丢弃本次结果
			if (token !== testToken) return;

			const status = res.error ? 'error' : 'success';
			const outputData = res.output || (res.error ? { error: res.error } : {});

			// 仅当用户还在看这个节点时，才展示结果到弹窗
			if (nodeTestDialog.nodeId === testNodeId) {
				nodeTestDialog.result = {
					status,
					outputData,
					timeCost: res.latencyMs || 0,
					error: res.error || undefined,
					isTimeout: !!res.isTimeout
				};

				if (status === 'success') {
					ElMessage.success(t('单节点测试完成'));
				} else if (res.isTimeout) {
					ElMessage.error(t('节点执行超时！'));
				}
			}

			// 同步写入会话级历史（回看/回填输入）与画布节点 runLog
			appendHistory(testNodeId, {
				time: new Date().toLocaleTimeString(),
				inputsJson: nodeTestDialog.form.inputsJson,
				outputData,
				timeCost: res.latencyMs || 0,
				error: res.error || undefined,
				status
			});

			// 同步写入画布节点 runLog，画布上节点下方也显示执行日志
			const node = elements.value.find(
				(el: any) => !('source' in el) && el.id === testNodeId
			) as FlowNode | undefined;
			if (node) {
				if (!node.data) node.data = { config: {} };
				node.data.runLog = {
					status,
					inputData: mockVariables,
					outputData,
					timeCost: res.latencyMs || 0
				};
			}
		} catch (err: any) {
			ElMessage.error(t('测试节点失败: ') + (err.message || err));
		} finally {
			// 仅当本次令牌仍最新时才复位 loading，避免覆盖新测试的 loading 状态
			if (token === testToken) {
				nodeTestDialog.loading = false;
			}
		}
	}

	function closeNodeTestDialog() {
		nodeTestDialog.visible = false;
	}

	/** 清理指定节点的测试输入缓存（节点删除时调用，避免内存泄漏） */
	function clearMockCache(nodeIds: string[]) {
		nodeIds.forEach(id => {
			delete mockVariablesCache[id];
		});
	}

	return {
		nodeTestDialog,
		nodeTestHistory,
		openNodeTestDialog,
		startNodeTest,
		closeNodeTestDialog,
		clearMockCache
	};
}
