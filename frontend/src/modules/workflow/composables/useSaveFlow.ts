import type { Ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { findInvalidNodeInput } from '../utils';

/**
 * 图拓扑校验纯函数（从 editor.vue 的 saveWorkflow 内联体抽出，便于单元测试）。
 *
 * 输入 nodes / edges 与翻译函数 t，返回人类可读的警告列表；空数组表示校验通过。
 * t 显式作为参数注入，避免依赖 composable 运行上下文，使本函数可直接单测。
 */
export function validateGraph(
	nodes: any[],
	edges: any[],
	t: (key: string) => string
): string[] {
	const warnings: string[] = [];

	// 2. 检查图结构完整性并给以提示
	const startNodes = nodes.filter(n => n.type === 'start');
	if (startNodes.length === 0) {
		warnings.push(t('工作流缺失"开始节点"，请在画布中添加唯一入口！'));
	} else if (startNodes.length > 1) {
		warnings.push(t('工作流存在多个"开始节点"，请在画布中保留唯一入口！'));
	}

	// 检查循环/批处理容器内部是否合法（多个起点或死循环）
	const groups = nodes.filter(n => n.type === 'loop_body_group');
	for (const g of groups) {
		const bodyNodeIds = nodes.filter(n => (n as any).parentNode === g.id).map(n => n.id);
		if (bodyNodeIds.length > 0) {
			const entries = bodyNodeIds.filter(
				nid => !edges.some(e => e.target === nid && bodyNodeIds.includes(e.source))
			);
			if (entries.length > 1) {
				const names = entries
					.map(eid => nodes.find(n => n.id === eid)?.label || eid)
					.join(', ');
				warnings.push(
					t('容器 "') +
						(g.label || g.id) +
						t('" 内存在多个没有输入的起点节点: ') +
						names +
						t('。请用内部连线明确它们的执行顺序！')
				);
			} else if (entries.length === 0) {
				warnings.push(
					t('容器 "') +
						(g.label || g.id) +
						t('" 内部形成了死循环闭环，无法确定起始节点！')
				);
			}
		}
	}

	// 检查 Switch 分支节点是否配置完整
	const switchNodes = nodes.filter(n => n.type === 'switch');
	for (const n of switchNodes) {
		const conf = n.data?.config || {};
		if (!conf.variable || !conf.variable.trim()) {
			warnings.push(t('节点"') + (n.label || n.id) + t('"未指定匹配变量名！'));
		}
		const cases = conf.cases || [];
		const seenCaseVals = new Set<string>();
		for (const c of cases) {
			if (!c.value || !c.value.trim()) {
				warnings.push(t('节点"') + (n.label || n.id) + t('"存在空白的 Case 匹配值！'));
			}
			if (c.value) {
				if (seenCaseVals.has(c.value.trim())) {
					warnings.push(
						t('节点"') +
							(n.label || n.id) +
							t('"中存在重复的 Case 匹配值：') +
							c.value.trim()
					);
				}
				seenCaseVals.add(c.value.trim());
			}
		}
	}

	// 检查结束节点是否配置完整
	const endNode = nodes.find(n => n.type === 'end');
	if (endNode) {
		const conf = endNode.data?.config || {};
		if (conf.outputFormat === 'json') {
			const fields = conf.outputFields || [];
			const seenFieldNames = new Set<string>();
			for (const f of fields) {
				if (!f.name || !f.name.trim()) {
					warnings.push(t('结束节点中存在未命名的输出字段！'));
				}
				if (f.name) {
					if (seenFieldNames.has(f.name.trim())) {
						warnings.push(t('结束节点中存在重复的输出字段名：') + f.name.trim());
					}
					seenFieldNames.add(f.name.trim());
				}
			}
		} else {
			if (!conf.outputTemplate || !conf.outputTemplate.trim()) {
				warnings.push(t('结束节点未配置输出结构模板！'));
			}
		}
	}

	// 检查孤立节点
	const connectedNodeIds = new Set<string>();
	edges.forEach(e => {
		if (e.source) connectedNodeIds.add(e.source);
		if (e.target) connectedNodeIds.add(e.target);
	});
	const isolatedNodes = nodes.filter(
		n =>
			n.type !== 'start' &&
			n.type !== 'end' &&
			!n.parentNode &&
			!connectedNodeIds.has(n.id)
	);
	if (isolatedNodes.length > 0) {
		warnings.push(
			t('发现孤立的工作节点：') +
				isolatedNodes.map(n => n.label || n.id).join(', ') +
				t('，请建立输入和输出连线！')
		);
	}

	// 检查模型节点是否已选择 Profile
	const modelRequiredTypes = ['llm', 'intent_classifier', 'image_generator'];
	const missingProfileNodes = nodes.filter(
		n =>
			modelRequiredTypes.includes(n.type) &&
			!(n.data?.config as any)?.modelProfileCode?.trim()
	);
	if (missingProfileNodes.length > 0) {
		warnings.push(
			t('以下节点未选择模型 Profile：') +
				missingProfileNodes.map(n => n.label || n.id).join(', ') +
				t('，请先在配置面板中选择模型！')
		);
	}

	// 检查是否存在重复的输出变量名（排除互斥条件分支）
	// 构建条件节点的互斥分组：同一条件节点不同分支上的节点互斥，不会同时执行
	const exclusiveGroups: Map<string, Set<string>> = new Map();
	const conditionalTypes = ['condition', 'intent_classifier', 'switch'];
	for (const n of nodes) {
		if (conditionalTypes.includes(n.type)) {
			const downstreamIds = edges.filter(e => e.source === n.id).map(e => e.target);
			if (downstreamIds.length > 1) {
				const group = new Set(downstreamIds);
				for (const id of downstreamIds) {
					exclusiveGroups.set(id, group);
				}
			}
		}
	}
	const varNameToNodes = new Map<string, string[]>();
	for (const n of nodes) {
		const outVar = (n.data?.config as any)?.outputVariable?.trim();
		if (outVar) {
			const list = varNameToNodes.get(outVar) || [];
			// 检查已有的同名节点是否与当前节点互斥
			// 首个节点 list 为空时 every 恒真，须显式要求 list 非空才视为互斥
			const isExclusive = list.length > 0 && list.every(existingLabel => {
				const existingNode = nodes.find(nn => (nn.label || nn.id) === existingLabel);
				if (!existingNode) return false;
				const groupA = exclusiveGroups.get(n.id);
				const groupB = exclusiveGroups.get(existingNode.id);
				return groupA && groupB && groupA === groupB;
			});
			if (isExclusive) continue;
			list.push(n.label || n.id);
			varNameToNodes.set(outVar, list);
		}
	}
	const duplicates = [...varNameToNodes.entries()].filter(([, ns]) => ns.length > 1);
	if (duplicates.length > 0) {
		const detail = duplicates
			.map(([varName, nodeNames]) => `${varName} (${nodeNames.join(', ')})`)
			.join('; ');
		warnings.push(t('输出变量名重复，后执行节点会覆盖先前结果：') + detail);
	}

	return warnings;
}

/**
 * 保存工作流 composable（从 editor.vue 抽出，修复批次2）。
 *
 * 职责：将画布 elements 校验并打包为草稿调用后端 saveDraft。
 * 校验逻辑见 {@link validateGraph}；序列化依赖 useGraphBuilder 提供的
 * buildGraphPayload / persistSignature。
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
