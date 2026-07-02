/** 命中的 group 矩形信息（已解析 style.width/height） */
export interface GroupRect {
	id: string;
	x: number;
	y: number;
	width: number;
	height: number;
}

/**
 * 判定点 (px, py) 是否落在某个 loop_body_group 矩形内，返回首个命中的 group。
 * 矩形宽高取自节点 style.width/height（缺省 400×250）。
 *
 * 用于：从工具栏拖入/放置节点时判定归属容器、dragover 时高亮目标容器。
 * 逻辑曾散落在 editor.vue 的 handleAddNode 与 onCanvasDragOver 两处（DRY 抽离）。
 */
export function hitTestGroup(elements: any[], px: number, py: number): GroupRect | undefined {
	for (const el of elements) {
		if ('source' in el || el.type !== 'loop_body_group') continue;
		const width = parseFloat(el.style?.width || '400');
		const height = parseFloat(el.style?.height || '250');
		const { x, y } = el.position;
		if (px >= x && px <= x + width && py >= y && py <= y + height) {
			return { id: el.id, x, y, width, height };
		}
	}
	return undefined;
}
