import { reactive, computed, type ComputedRef, type Ref } from 'vue';
import { UNTESTABLE_NODE_TYPES } from '../components/constants';

/** 右键菜单状态 */
export interface ContextMenuState {
	visible: boolean;
	x: number;
	y: number;
	nodeId: string;
}

/**
 * 右键菜单 composable（从 editor.vue 抽出）。
 *
 * 收纳菜单的显隐/位置/目标节点状态、可测试与可分布的计算属性，
 * 以及边界检测（clampMenuPosition）与打开/关闭。
 *
 * 键盘 a11y（方向键/Enter/Escape、打开聚焦）在 context-menu.vue 组件内，
 * 菜单项的业务动作（编辑/测试/复制/分布/删除）由父组件响应组件 emit 处理。
 *
 * @param elements 画布元素 ref
 * @param getSelectedNodes 当前选中节点（来自 useVueFlow），用于判断是否可等距分布
 */
export function useContextMenu(elements: Ref<any[]>, getSelectedNodes: ComputedRef<any[]>) {
	const contextMenu = reactive<ContextMenuState>({
		visible: false,
		x: 0,
		y: 0,
		nodeId: ''
	});

	// 当前右键节点是否可单独测试（排除不支持测试的节点类型）
	const canTestContextNode = computed(() => {
		if (!contextMenu.nodeId) return false;
		const node = elements.value.find(el => !('source' in el) && el.id === contextMenu.nodeId);
		if (!node) return false;
		return !UNTESTABLE_NODE_TYPES.includes(node.type);
	});

	// 是否可执行等距分布（至少选中 3 个节点）
	const canDistribute = computed(() => getSelectedNodes.value.length >= 3);

	// 右键菜单边界检测：靠近视口右下边界时向左/上展开，避免溢出
	function clampMenuPosition(x: number, y: number) {
		const menuW = 180;
		const menuH = 180;
		const vw = window.innerWidth;
		const vh = window.innerHeight;
		return {
			x: x + menuW > vw ? x - menuW : x,
			y: y + menuH > vh ? y - menuH : y
		};
	}

	/** 在 (x, y) 处对 nodeId 打开菜单（自动边界回弹） */
	function openContextMenu(nodeId: string, x: number, y: number) {
		const pos = clampMenuPosition(x, y);
		contextMenu.visible = true;
		contextMenu.x = pos.x;
		contextMenu.y = pos.y;
		contextMenu.nodeId = nodeId;
	}

	/** 关闭菜单并清空目标 nodeId */
	function closeContextMenu() {
		contextMenu.visible = false;
		contextMenu.nodeId = '';
	}

	return { contextMenu, canTestContextNode, canDistribute, openContextMenu, closeContextMenu };
}
