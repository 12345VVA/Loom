import type { Ref } from 'vue';

/**
 * 图构建 composable
 * 负责将画布 elements 转换为后端标准的拓扑 JSON（buildGraphPayload），
 * 以及计算剥离运行态字段后的拓扑签名（persistSignature）。
 *
 * 从 editor.vue 抽出（修复批次1），使核心序列化逻辑可独立单元测试。
 * 入参沿用 useUndoRedo 的 Ref<any[]> 模式，避免与 editor.vue 局部 FlowNode/FlowEdge 类型耦合。
 */
export function useGraphBuilder(elements: Ref<any[]>) {
	/**
	 * 计算剥离运行态字段（class、data.runLog/runData）后的拓扑签名。
	 * 用于区分"真实编辑"与"试运行/单节点测试写入的运行态"，
	 * 避免后者污染 isDirty、误清上游缓存。
	 */
	function persistSignature(els: any[]): string {
		return JSON.stringify(
			els.map((el: any) => {
				if (!el) return el;
				const { class: _class, ...rest } = el;
				if (rest && rest.data) {
					const { runLog: _runLog, runData: _runData, ...dataRest } = rest.data;
					rest.data = dataRest;
				}
				return rest;
			})
		);
	}

	/**
	 * 构建后端标准的拓扑 JSON 结构。
	 * - nodes/edges：执行用标准结构
	 * - elements：画布还原用（保留 argumentsJson 等编辑态字段）
	 */
	function buildGraphPayload() {
		const nodes = elements.value.filter(el => !('source' in el));
		const edges = elements.value.filter(el => 'source' in el);

		// 剥离运行态数据 (runLog 等) 防止被错误保存并造成体积膨胀
		const cleanElements = elements.value.map(el => {
			if ('source' in el) return el;
			const { class: _, ...restNode } = el;
			const data = { ...(restNode.data || {}) };
			delete data.runLog;
			return { ...restNode, data };
		});

		return {
			elements: cleanElements,
			nodes: nodes.map((n: any) => {
				const conf = { ...(n.data?.config || {}) };
				if (n.type === 'tool_executor') {
					try {
						conf.arguments = JSON.parse(conf.argumentsJson || '{}');
					} catch {
						conf.arguments = {};
					}
					// [P0 修复] arguments 已解析为对象，删除冗余的字符串字段，
					// 避免 nodes[].config 同时携带 arguments + argumentsJson
					delete conf.argumentsJson;
				}
				const serialized: any = {
					id: n.id,
					type: n.type,
					name: n.label,
					config: conf
				};
				if (n.parentNode) serialized.parentNode = n.parentNode;
				if (n.extent) serialized.extent = n.extent;
				if (n.expandParent) serialized.expandParent = n.expandParent;
				if (n.style) serialized.style = n.style;
				return serialized;
			}),
			edges: edges.map((e: any) => {
				const edge: any = {
					source: e.source,
					target: e.target,
					type: e.type || 'direct',
					condition: e.data?.condition || ''
				};
				if (e.sourceHandle) edge.sourceHandle = e.sourceHandle;
				if (e.data?.label) edge.data = { label: e.data.label };
				return edge;
			})
		};
	}

	return { persistSignature, buildGraphPayload };
}
