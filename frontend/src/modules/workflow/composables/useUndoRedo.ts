import { ref, computed, type Ref } from 'vue';

interface Snapshot {
	elements: any[];
}

/**
 * 撤销/重做 composable
 * 管理 elements 的历史快照，支持 Ctrl+Z / Ctrl+Shift+Z
 */
export function useUndoRedo(elements: Ref<any[]>) {
	const history = ref<Snapshot[]>([]);
	const pointer = ref(-1);
	const MAX_HISTORY = 50;

	const canUndo = computed(() => pointer.value > 0);
	const canRedo = computed(() => pointer.value < history.value.length - 1);

	/**
	 * 深拷贝当前 elements 并存入历史栈
	 */
	function pushSnapshot() {
		// 截断当前位置之后的历史（新操作覆盖 redo 栈）
		history.value = history.value.slice(0, pointer.value + 1);

		const snapshot: Snapshot = {
			elements: JSON.parse(JSON.stringify(elements.value))
		};
		history.value.push(snapshot);

		// 限制历史长度
		if (history.value.length > MAX_HISTORY) {
			history.value.shift();
		} else {
			pointer.value = history.value.length - 1;
		}
	}

	/**
	 * 撤销：恢复上一个快照
	 */
	function undo(): boolean {
		if (!canUndo.value) return false;
		pointer.value--;
		elements.value = JSON.parse(JSON.stringify(history.value[pointer.value].elements));
		return true;
	}

	/**
	 * 重做：恢复下一个快照
	 */
	function redo(): boolean {
		if (!canRedo.value) return false;
		pointer.value++;
		elements.value = JSON.parse(JSON.stringify(history.value[pointer.value].elements));
		return true;
	}

	/**
	 * 初始化：存入当前状态作为第一个快照
	 */
	function init() {
		history.value = [];
		pointer.value = -1;
		pushSnapshot();
	}

	return {
		canUndo,
		canRedo,
		pushSnapshot,
		undo,
		redo,
		init
	};
}
