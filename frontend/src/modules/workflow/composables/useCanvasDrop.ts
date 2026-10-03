import { type Ref } from 'vue';

import type { FlowEdge, FlowNode } from '../types/editor';
import { hitTestGroup } from '../utils/group-hit-test';

/**
 * 画布拖放交互 composable
 * 侧边栏拖入 / 点击添加节点、group 容器拖入高亮、节点等距分布
 */
export function useCanvasDrop(options: {
	elements: Ref<(FlowNode | FlowEdge)[]>;
	/** vue-flow 屏幕坐标 → 画布坐标投影（useVueFlow().project） */
	project: (point: { x: number; y: number }) => { x: number; y: number };
	handleAddNode: (type: string, x: number, y: number) => void;
	getSelectedNodes: Ref<FlowNode[]>;
	pushSnapshot: () => void;
	closeContextMenu: () => void;
}) {
	const { elements, project, handleAddNode, getSelectedNodes, pushSnapshot, closeContextMenu } = options;

	/** 侧边栏拖拽开始记录节点类型 */
	function onDragStart(event: DragEvent, type: string) {
		if (event.dataTransfer) {
			event.dataTransfer.setData('application/vueflow', type);
			event.dataTransfer.effectAllowed = 'move';
		}
	}

	/** 通过点击面板添加节点（放置于画布中心） */
	function onAddNodeClick(type: string) {
		// 获取画布中心
		const wrapper = document.querySelector('.vue-flow');
		if (!wrapper) return;
		const rect = wrapper.getBoundingClientRect();

		const centerX = rect.width / 2;
		const centerY = rect.height / 2;

		// 投影到 vue-flow 坐标系
		const pos = project({ x: centerX, y: centerY });
		handleAddNode(type, pos.x - 50, pos.y - 20);
	}

	/** 画布放置时实例化新节点 */
	function onDrop(event: DragEvent) {
		const type = event.dataTransfer?.getData('application/vueflow');
		if (!type) return;

		// 计算在画布内的放置坐标
		const react = event.currentTarget as HTMLElement;
		const bounds = react.getBoundingClientRect();

		// 首先投影鼠标所在的真实屏幕相对坐标
		const projected = project({
			x: event.clientX - bounds.left,
			y: event.clientY - bounds.top
		});

		// 在 VueFlow 坐标系中减去节点的半宽和半高，使其在鼠标居中
		handleAddNode(type, projected.x - 50, projected.y - 20);
	}

	/** 画布 dragover：group 容器拖入高亮 */
	function onCanvasDragOver(event: DragEvent) {
		document
			.querySelectorAll('.loop-body-group-node.is-drag-over')
			.forEach(el => el.classList.remove('is-drag-over'));
		const type = event.dataTransfer?.getData('application/vueflow');
		if (!type || type === 'loop_body_group') return;

		const canvasEl = document.querySelector('.canvas-wrapper');
		if (!canvasEl) return;
		const bounds = canvasEl.getBoundingClientRect();
		const flowX = event.clientX - bounds.left;
		const flowY = event.clientY - bounds.top;

		// 命中判定见 utils/group-hit-test.ts
		const hit = hitTestGroup(elements.value, flowX, flowY);
		if (hit) {
			const domNode = document.querySelector(`[data-id="${hit.id}"] .loop-body-group-node`);
			if (domNode) domNode.classList.add('is-drag-over');
		}
	}

	/** 拖拽离开画布：清除所有 group 容器的高亮态 */
	function onCanvasDragLeave() {
		document
			.querySelectorAll('.loop-body-group-node.is-drag-over')
			.forEach(el => el.classList.remove('is-drag-over'));
	}

	/** 水平等距分布：以最左/最右节点为界，等间距重排中间节点的 x 坐标 */
	function distributeHorizontal() {
		const selected = getSelectedNodes.value;
		if (selected.length < 3) return;
		selected.sort((a, b) => a.position.x - b.position.x);
		const minX = selected[0].position.x;
		const maxX = selected[selected.length - 1].position.x;
		const step = (maxX - minX) / (selected.length - 1);
		selected.forEach((node, i) => {
			if (i > 0 && i < selected.length - 1) {
				node.position.x = minX + step * i;
			}
		});
		pushSnapshot();
		closeContextMenu();
	}

	/** 垂直等距分布：以最上/最下节点为界，等间距重排中间节点的 y 坐标 */
	function distributeVertical() {
		const selected = getSelectedNodes.value;
		if (selected.length < 3) return;
		selected.sort((a, b) => a.position.y - b.position.y);
		const minY = selected[0].position.y;
		const maxY = selected[selected.length - 1].position.y;
		const step = (maxY - minY) / (selected.length - 1);
		selected.forEach((node, i) => {
			if (i > 0 && i < selected.length - 1) {
				node.position.y = minY + step * i;
			}
		});
		pushSnapshot();
		closeContextMenu();
	}

	return {
		onDragStart,
		onAddNodeClick,
		onDrop,
		onCanvasDragOver,
		onCanvasDragLeave,
		distributeHorizontal,
		distributeVertical
	};
}
