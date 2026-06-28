import { ref, computed } from 'vue';

interface GuideLine {
	type: 'horizontal' | 'vertical';
	position: number;
}

/**
 * 对齐辅助线 composable
 * 在拖动节点时检测与其他节点的水平/垂直对齐关系，生成参考线
 */
export function useAlignmentGuides() {
	const guides = ref<GuideLine[]>([]);
	const ALIGN_THRESHOLD = 5;

	/**
	 * 在节点拖动过程中计算对齐辅助线
	 * @param dragNodeId 当前正在拖动的节点 ID
	 * @param dragNodePos 当前拖动节点的位置 { x, y }
	 * @param allNodes 所有节点数组（包含 id, position, type 等）
	 */
	function computeGuides(
		dragNodeId: string,
		dragNodePos: { x: number; y: number },
		allNodes: Array<{ id: string; position: { x: number; y: number }; type?: string }>
	) {
		const newGuides: GuideLine[] = [];
		const dragX = dragNodePos.x;
		const dragY = dragNodePos.y;

		for (const node of allNodes) {
			if (node.id === dragNodeId) continue;
			if (node.type === 'loop_body_group') continue; // 跳过容器节点

			const nx = node.position.x;
			const ny = node.position.y;

			// 垂直对齐（节点左侧 x 坐标接近）
			if (Math.abs(dragX - nx) < ALIGN_THRESHOLD) {
				newGuides.push({ type: 'vertical', position: Math.min(dragX, nx) });
			}
			// 水平对齐（节点顶部 y 坐标接近）
			if (Math.abs(dragY - ny) < ALIGN_THRESHOLD) {
				newGuides.push({ type: 'horizontal', position: Math.min(dragY, ny) });
			}
		}

		guides.value = newGuides;
	}

	/**
	 * 清除所有辅助线（松开鼠标时调用）
	 */
	function clearGuides() {
		guides.value = [];
	}

	return {
		guides,
		computeGuides,
		clearGuides
	};
}
