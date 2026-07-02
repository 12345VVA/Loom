import type { Ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { findInvalidNodeInput } from '../utils';
import { validateGraph } from '../utils/graph-validator';

/**
 * 保存工作流 composable（从 editor.vue 抽出，修复批次2）。
 *
 * 职责：将画布 elements 校验并打包为草稿调用后端 saveDraft。
 * 校验逻辑见 utils/graph-validator.ts 的 validateGraph（纯函数，独立单测）；
 * 序列化依赖 useGraphBuilder 提供的 buildGraphPayload / persistSignature。
 *
 * 保存成功后通过 onSaved 回调通知调用方重置 isDirty 基线签名（_persistSig），
 * 避免 composable 直接持有 editor.vue 的模块级闭包变量。
 */
export function useSaveFlow(opts: {
	elements: Ref<any[]>;
	saving: Ref<boolean>;
	isDirty: Ref<boolean>;
	workflowId: Ref<any>;
	workflowCode: Ref<string>;
	workflowName: Ref<string>;
	workflowDescription: Ref<string>;
	service: any;
	buildGraphPayload: () => any;
	persistSignature: (els: any[]) => string;
	onSaved?: (newSig: string) => void;
}) {
	const { t } = useI18n();

	// 将 Vue Flow 画布信息转换打包为后端标准工作流 JSON 格式并存储
	async function saveWorkflow(): Promise<boolean> {
		if (!opts.workflowId.value) return false;
		// [P0 修复] 并发互斥：快速双击保存时阻止重入，避免竞态写入
		if (opts.saving.value) return false;
		// 阻断：节点 inputs 变量名非法（空/格式错/重名）时不允许保存
		const invalidInput = findInvalidNodeInput(opts.elements.value);
		if (invalidInput) {
			ElMessage.warning(invalidInput.error);
			return false;
		}
		opts.saving.value = true;
		try {
			// 1. 拆分连线与节点 (TS-safe 属性检查)
			const nodes = opts.elements.value.filter(el => !('source' in el));
			const edges = opts.elements.value.filter(el => 'source' in el);

			// 2. 校验图结构完整性
			const warnings = validateGraph(nodes, edges, t);
			if (warnings.length > 0) {
				ElMessageBox.alert(
					warnings.map((w, idx) => `${idx + 1}. ${w}`).join('<br>'),
					t('保存失败 (检测到拓扑问题)'),
					{
						confirmButtonText: t('确定'),
						type: 'error',
						dangerouslyUseHTMLString: true
					}
				);
				return false;
			}

			// 3. 验证并构造后端标准解析结构
			const graphPayload = opts.buildGraphPayload();

			// 4. 保存草稿（纯版本表模型：graph 存版本表草稿，未发布不上线）
			await opts.service.workflow.definition.saveDraft({
				definitionId: Number(opts.workflowId.value),
				code: opts.workflowCode.value,
				name: opts.workflowName.value,
				description: opts.workflowDescription.value,
				graphJson: JSON.stringify(graphPayload)
			});

			ElMessage.success(t('草稿保存成功（发布后生效）'));
			opts.isDirty.value = false;
			// 保存成功：以当前拓扑签名重置 isDirty 比较基线
			opts.onSaved?.(opts.persistSignature(opts.elements.value));
			return true;
		} catch (err: any) {
			ElMessage.error(t('保存失败: ') + (err.message || err));
			return false;
		} finally {
			opts.saving.value = false;
		}
	}

	return { saveWorkflow };
}
