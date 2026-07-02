import { type Ref } from 'vue';

import type { FlowNode, FlowEdge } from '../types/editor';

export interface UpstreamVariable {
	nodeId: string;
	nodeLabel: string;
	variableName: string;
	nodeType: string;
	jsonFields?: any[];
	_isLoopContext?: boolean;
}

/**
 * 上游变量收集 composable（从 editor.vue 抽出，便于单元测试）。
 *
 * 收集指定节点的全部上游可达变量（start 输入变量、各节点 outputVariable、循环上下文变量），
 * 供配置面板的变量引用下拉与单节点测试使用。内部递归溯源上游并去环。
 *
 * 带 elements 版本号的缓存：拓扑变化（invalidateUpstreamCache）后整体失效，
 * 避免每次选中节点都重跑溯源。
 */
export function useUpstreamVariables(elements: Ref<any[]>) {
	const _upstreamCache = new Map<string, { result: UpstreamVariable[]; version: number }>();
	let _elementsVersion = 0;

	/** 通知拓扑已变化，失效全部上游变量缓存（应在检测到真实编辑时调用） */
	function invalidateUpstreamCache() {
		_elementsVersion++;
		_upstreamCache.clear();
	}

	/** 收集指定节点的全部上游可达变量（递归溯源、去环，含循环上下文变量） */
	function getUpstreamVariablesForNode(nodeId: string): UpstreamVariable[] {
		const result: UpstreamVariable[] = [];
		const visited = new Set<string>();

		const targetNode = elements.value.find(el => !('source' in el) && el.id === nodeId) as
			| FlowNode
			| undefined;
		if (!targetNode) return result;

		function traceUpstream(currentId: string) {
			if (visited.has(currentId)) return;
			visited.add(currentId);
			const incomingEdges = elements.value.filter(
				(el: any) => 'source' in el && el.target === currentId
			) as FlowEdge[];
			for (const edge of incomingEdges) {
				const src = elements.value.find(
					(el: any) => !('source' in el) && el.id === edge.source
				) as FlowNode | undefined;
				if (!src) continue;
				if (src.type === 'start') {
					if (visited.has(src.id)) continue;
					visited.add(src.id);
					const inputVars: string[] = (src.data?.config as any)?.inputVariables || [];
					for (const varName of inputVars) {
						if (varName && varName.trim()) {
							result.push({
								nodeId: src.id,
								nodeLabel: src.label,
								variableName: varName.trim(),
								nodeType: src.type
							});
						}
					}
				} else {
					const cfg = src.data?.config || {};
					const outputVar = (cfg as any).outputVariable || '';
					if (outputVar) {
						const entry: UpstreamVariable = {
							nodeId: src.id,
							nodeLabel: src.label,
							variableName: outputVar,
							nodeType: src.type
						};
						if (src.type === 'llm' && (cfg as any).outputFormat === 'json') {
							entry.jsonFields = (cfg as any).jsonFields || [];
						}
						result.push(entry);
					}
					traceUpstream(src.id);
				}
			}
		}
		traceUpstream(nodeId);

		// 循环上下文变量注入
		const parentId = (targetNode as any).parentNode;
		if (parentId) {
			const groupNode = elements.value.find(el => !('source' in el) && el.id === parentId) as
				| FlowNode
				| undefined;
			if (groupNode?.type === 'loop_body_group') {
				const ctrlId = groupNode.data?.config?.controllerNodeId;
				if (ctrlId) {
					const ctrlNode = elements.value.find(
						el => !('source' in el) && el.id === ctrlId
					) as FlowNode | undefined;
					if (ctrlNode) {
						const itemVar = ctrlNode.data?.config?.itemVariable || 'loop_item';
						result.unshift({
							nodeId: ctrlNode.id,
							nodeLabel: ctrlNode.label,
							variableName: itemVar,
							nodeType: ctrlNode.type,
							_isLoopContext: true
						});
					}
				}
			}
		}

		return result;
	}

	/** 当前选中节点的上游变量（带版本缓存）；nodeId 为空时返回 [] */
	function upstreamVariablesOf(nodeId: string | null | undefined): UpstreamVariable[] {
		if (!nodeId) return [];
		const cached = _upstreamCache.get(nodeId);
		if (cached && cached.version === _elementsVersion) {
			return cached.result;
		}
		const result = getUpstreamVariablesForNode(nodeId);
		_upstreamCache.set(nodeId, { result, version: _elementsVersion });
		return result;
	}

	return { getUpstreamVariablesForNode, upstreamVariablesOf, invalidateUpstreamCache };
}
