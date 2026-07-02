/**
 * 根据源节点类型与 sourceHandle 推导连线标签。
 *
 * - condition → True / False
 * - switch → 命中 case 的 value / 默认
 * - intent_classifier → 命中 intent 的 name / 默认
 *
 * 从 editor.vue 抽出为纯函数。旧的下标格式（case_N / intent_N）兜底已移除
 * （激进清理：示例数据均用稳定 id 格式 case_<id> / intent_<id>）。
 */
export function getEdgeLabel(
	sourceHandle: string | undefined,
	srcNode: any
): string | undefined {
	if (!srcNode) return undefined;
	if (srcNode.type === 'condition') {
		if (sourceHandle === 'true') return 'True';
		if (sourceHandle === 'false') return 'False';
	}
	if (srcNode.type === 'switch') {
		if (sourceHandle === 'default') return '默认';
		if (sourceHandle?.startsWith('case_')) {
			const id = sourceHandle.slice(5);
			const byId = srcNode.data?.config?.cases?.find((c: any) => c.id === id);
			return byId?.value || 'Case';
		}
	}
	if (srcNode.type === 'intent_classifier') {
		if (sourceHandle === 'default') return '默认';
		if (sourceHandle?.startsWith('intent_')) {
			const id = sourceHandle.slice(7);
			const byId = srcNode.data?.config?.intents?.find((i: any) => i.id === id);
			return byId?.name || 'Intent';
		}
	}
	return undefined;
}
