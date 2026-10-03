import { type Ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import dayjs from 'dayjs';

import type { FlowEdge, FlowNode } from '../types/editor';
import { migrateLoadedElements } from '../utils/graph-migration';

/**
 * 工作流加载 / 发布 / 导出 composable
 */
export function useWorkflowIO(options: {
	service: any;
	workflowId: Ref<string | null>;
	workflowName: Ref<string>;
	workflowCode: Ref<string>;
	workflowDescription: Ref<string>;
	elements: Ref<(FlowNode | FlowEdge)[]>;
	aiProfiles: Ref<Eps.profile[]>;
	buildGraphPayload: () => any;
	persistSignature: (els: (FlowNode | FlowEdge)[]) => string;
	initUndoRedo: () => void;
	/** 加载/新建完成：以当前拓扑签名（已剥离运行态字段）重置 isDirty 比较基线 */
	onLoaded: (sig: string) => void;
	saveWorkflow: () => Promise<boolean>;
}) {
	const {
		service,
		workflowId,
		workflowName,
		workflowCode,
		workflowDescription,
		elements,
		aiProfiles,
		buildGraphPayload,
		persistSignature,
		initUndoRedo,
		onLoaded,
		saveWorkflow
	} = options;
	const { t } = useI18n();

	/** 拉取工作流详情并还原画布拓扑：解析草稿 JSON、兼容旧版字段/handle 格式迁移；无草稿时初始化默认开始-结束节点 */
	async function fetchWorkflowData() {
		try {
			const res = await service.workflow.definition.info({ id: workflowId.value });
			workflowName.value = res.name;
			workflowCode.value = res.code;
			workflowDescription.value = res.description || '';

			// 加载草稿拓扑（纯版本表模型：graph 存版本表，info 回填 draftGraphJson）
			if (res.draftGraphJson && res.draftGraphJson !== '{}') {
				const graph = JSON.parse(res.draftGraphJson);

				// 加载后字段迁移/适配（纯函数，见 utils/graph-migration.ts）：
				// 仅保留 tool_executor arguments→argumentsJson 编辑态适配、switch/intent 稳定 id 补全。
				// 旧版本兼容（默认值补全、sourceHandle 下标/反向重建）已激进清理。
				const loadedElements = migrateLoadedElements(graph.elements || []);

				elements.value = loadedElements;
			} else {
				// 初始化一个"开始"和"结束"的默认节点
				elements.value = [
					{
						id: 'node_start',
						type: 'start',
						label: t('开始'),
						position: { x: 100, y: 150 },
						data: { config: { inputVariables: ['query'] } }
					},
					{
						id: 'node_end',
						type: 'end',
						label: t('结束'),
						position: { x: 600, y: 150 },
						data: { config: { outputFormat: 'json', outputFields: [] } }
					}
				];
			}
			initUndoRedo();
			// 加载/新建完成：以当前拓扑签名（已剥离运行态字段）作为 isDirty 比较基线
			onLoaded(persistSignature(elements.value));
		} catch (e) {
			ElMessage.error(t('获取工作流详情失败'));
		}
	}

	/** 拉取可配置的大模型列表，供 LLM/图像生成等节点选择模型 */
	async function fetchAiProfiles() {
		try {
			const list = await service.ai.profile.list({});
			aiProfiles.value = list;
		} catch (e) {
			console.error('Fetch AI profiles failed', e);
		}
	}

	/** 发布草稿：先保存最新草稿，再 publish（一步上线；运行中实例按其版本继续跑、不受影响） */
	async function publishWorkflow() {
		if (!workflowId.value) return;
		try {
			await ElMessageBox.confirm(
				t('发布后新启动的实例将使用此版本，正在运行的实例按其版本继续跑、不受影响。是否先保存并发布？'),
				t('发布'),
				{ type: 'warning' }
			);
		} catch {
			return; // 用户取消
		}
		const saved = await saveWorkflow();
		if (!saved) return;
		try {
			await service.workflow.version.publish({ definitionId: Number(workflowId.value) });
			ElMessage.success(t('发布成功'));
			await fetchWorkflowData();
		} catch (err: any) {
			ElMessage.error(t('发布失败: ') + (err.message || err));
		}
	}

	/** 导出工作流 */
	function exportWorkflow() {
		if (!workflowId.value) return;

		const exportData = {
			version: '1.0',
			type: 'LoomWorkflow',
			metadata: {
				name: workflowName.value,
				description: workflowDescription.value
			},
			graph_json: JSON.stringify(buildGraphPayload())
		};

		const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		const dateStr = dayjs().format('YYYYMMDD');
		a.download = `LoomWorkflow_${workflowName.value || 'Untitled'}_${dateStr}.json`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);

		ElMessage.success(t('导出成功'));
	}

	return { fetchWorkflowData, fetchAiProfiles, publishWorkflow, exportWorkflow };
}
