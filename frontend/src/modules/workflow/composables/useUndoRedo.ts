import { ref, computed, type Ref } from 'vue';

interface Snapshot {
	elements: any[];
}

/**
 * 深拷贝：优先 structuredClone（保真 Date/Map/Set 等 JSON 无法保留的类型），
 * 不可结构化克隆时（如含 Vue 组件引用、函数）回退 JSON。
 * 注意：elements 节点的 icon 字段是 Vue 组件引用，structuredClone 会抛 DataCloneError，
 * 故必须保留 JSON 兜底，否则 undo/redo 会直接崩溃。
 */
function deepClone<T>(value: T): T {
	if (typeof structuredClone === 'function') {
		try {
			return structuredClone(value);
		} catch {
			// 回退 JSON（结构化克隆失败，通常因含函数/组件引用）
		}
	}
	return JSON.parse(JSON.stringify(value));
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
			elements: deepClone(elements.value)
		};
		history.value.push(snapshot);

		// 限制历史长度；无论是否 shift，pointer 都统一指向新的栈顶
		if (history.value.length > MAX_HISTORY) {
			history.value.shift();
		}
		pointer.value = history.value.length - 1;
	}

	/**
	 * 撤销：恢复上一个快照
	 */
	function undo(): boolean {
		if (!canUndo.value) return false;
		pointer.value--;
		elements.value = deepClone(history.value[pointer.value].elements);
		return true;
	}

	/**
	 * 重做：恢复下一个快照
	 */
	function redo(): boolean {
		if (!canRedo.value) return false;
		pointer.value++;
		elements.value = deepClone(history.value[pointer.value].elements);
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
