/**
 * 节点操作工具（纯决策函数）
 * 从 editor.vue 抽出"删除级联 + 子节点坐标转换"的纯计算逻辑，便于单元测试。
 * 有状态副作用（写入 elements.value、pushSnapshot、UI 反馈）仍留在 editor.vue。
 */

export interface RemovalPlan {
	/** 显式要删除的节点 id */
	nodeIds: string[];
	/** 显式要删除的连线 id（批量删除时可能选中 edge） */
	edgeIds?: string[];
}

/**
 * 计算删除一批节点后的新 elements（不可变）：
 * 1. 级联：删 loop_controller/batch_processor 时连带其 loop_body_group，反之亦然
 *    （修复 P0：原三处删除路径均不清理关联 group，产生孤儿 group）
 * 2. 删除节点 + 相关连线（端点命中被删节点 / 显式选中的 edge）
 * 3. 解除子节点 parentNode 时，将相对坐标转为绝对坐标
 *    （修复 P0：原仅 delete parentNode 导致子节点渲染位置错乱）
 */
export function planNodeRemoval(elements: any[], plan: RemovalPlan): any[] {
	const nodeIds = new Set(plan.nodeIds);
	const edgeIds = new Set(plan.edgeIds ?? []);

	// 1. 级联：controller ↔ group 双向连带
	for (const el of elements) {
		if ('source' in el || !nodeIds.has(el.id)) continue;
		if (el.type === 'loop_controller' || el.type === 'batch_processor') {
			const grp = elements.find(
				(g: any) => !('source' in g) && g.type === 'loop_body_group' && g.data?.config?.controllerNodeId === el.id
			);
			if (grp) nodeIds.add(grp.id);
		} else if (el.type === 'loop_body_group') {
			const ctrlId = el.data?.config?.controllerNodeId;
			if (ctrlId) nodeIds.add(ctrlId);
		}
	}

	// 被删 group 的绝对坐标（用于其子节点坐标转换）
	const groupPos = new Map<string, { x: number; y: number }>();
	for (const el of elements) {
		if (!('source' in el) && nodeIds.has(el.id) && el.type === 'loop_body_group') {
			groupPos.set(el.id, el.position);
		}
	}

	// 2 & 3. 过滤删除 + 子节点 parentNode 解除并转绝对坐标
	return elements
		.filter((el: any) => {
			if ('source' in el) {
				return !edgeIds.has(el.id) && !nodeIds.has(el.source) && !nodeIds.has(el.target);
			}
			return !nodeIds.has(el.id);
		})
		.map((el: any) => {
			if (!('source' in el) && el.parentNode && nodeIds.has(el.parentNode)) {
				const gp = groupPos.get(el.parentNode);
				const position = gp ? { x: el.position.x + gp.x, y: el.position.y + gp.y } : el.position;
				const { parentNode: _pn, expandParent: _ep, ...rest } = el;
				return { ...rest, position };
			}
			return el;
		});
}
