import { type Ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router';

/**
 * 快捷键指南清单（单一来源）：与 handleKeyDown 的实现一一对应，
 * 新增/删除快捷键时必须同步本清单，画布快捷键指南对话框由此派生渲染。
 * keys 的 mod 占位符在渲染时按平台替换为 Ctrl / ⌘。
 */
export const SHORTCUT_DEFS: readonly { descKey: string; keys: readonly string[] }[] = [
	{ descKey: '保存工作流', keys: ['mod', 'S'] },
	{ descKey: '撤销操作', keys: ['mod', 'Z'] },
	{ descKey: '重做操作', keys: ['mod', 'Shift+Z / Y'] },
	{ descKey: '试运行工作流（草稿）', keys: ['mod', 'Enter'] },
	{ descKey: '测试选中节点', keys: ['mod', 'Shift', 'T'] },
	{ descKey: '复制选中节点', keys: ['mod', 'D'] },
	{ descKey: '删除选中节点/边', keys: ['Delete / Backspace'] },
	{ descKey: '关闭配置面板/菜单', keys: ['Esc'] },
	{ descKey: '画布缩放', keys: ['滚轮'] },
	{ descKey: '画布平移', keys: ['鼠标按住背景拖动'] }
];

/**
 * 编辑器键盘快捷键与路由守卫 composable
 * Esc 关闭面板/菜单、Ctrl+S 保存、Ctrl+Z/Shift+Z 撤销/重做、Ctrl+D 复制选中节点、
 * Delete/Backspace 删除选中元素、Ctrl/Cmd+Enter 试运行、Ctrl+Shift+T 测试选中节点；
 * 未保存修改时，离开编辑器或切换工作流前提示。
 */
export function useKeyboardShortcuts(deps: {
	selectedNodeId: Ref<string | null>;
	isDirty: Ref<boolean>;
	closeContextMenu: () => void;
	saveWorkflow: () => boolean | Promise<boolean>;
	undo: () => boolean;
	redo: () => boolean;
	deleteSelectedElements: () => void;
	duplicateSelectedElements: () => void;
	openTestDialog: () => void;
	openNodeTestDialog: (nodeId: string) => void;
}) {
	const {
		selectedNodeId,
		isDirty,
		closeContextMenu,
		saveWorkflow,
		undo,
		redo,
		deleteSelectedElements,
		duplicateSelectedElements,
		openTestDialog,
		openNodeTestDialog
	} = deps;
	const { t } = useI18n();
	const route = useRoute();

	// 未保存修改时，离开编辑器或切换工作流前提示，避免误丢编辑
	async function confirmDiscardIfDirty(): Promise<boolean> {
		if (!isDirty.value) return true;
		try {
			await ElMessageBox.confirm(
				t('当前工作流有未保存的修改，继续将丢弃这些修改。'),
				t('未保存提示'),
				{ type: 'warning', confirmButtonText: t('放弃修改'), cancelButtonText: t('取消') }
			);
			return true;
		} catch {
			return false;
		}
	}

	// 离开编辑器到其他页面
	onBeforeRouteLeave(async () => {
		if (!(await confirmDiscardIfDirty())) return false;
	});

	// 同组件切换工作流（/editor?id=A → /editor?id=B）
	onBeforeRouteUpdate(async to => {
		if (String(to.query.id ?? '') !== String(route.query.id ?? '')) {
			if (!(await confirmDiscardIfDirty())) return false;
		}
	});

	// 全局键盘快捷键
	function handleKeyDown(event: KeyboardEvent) {
		// 仅 Delete/Backspace 需要避开输入控件（防止打字误删画布元素）；
		// 带修饰键的 Ctrl+S/Z/D/Enter 与 Esc 在输入控件聚焦时照常生效——
		// 此前一刀切豁免导致 CodeMirror/输入框内按 Ctrl+S 既不保存工作流、
		// 又不 preventDefault 而弹出浏览器"保存网页"对话框
		if (event.key === 'Escape') {
			selectedNodeId.value = null;
			closeContextMenu();
		}

		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
			event.preventDefault();
			saveWorkflow();
		}

		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
			event.preventDefault();
			if (event.shiftKey) {
				if (redo()) ElMessage.info(t('已重做'));
			} else {
				if (undo()) ElMessage.info(t('已撤销'));
			}
		}

		// Ctrl/Cmd+Y：重做的通用别名（与 Ctrl+Shift+Z 等价）
		if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'y') {
			event.preventDefault();
			if (redo()) ElMessage.info(t('已重做'));
		}

		// Ctrl/Cmd+Enter：整图试运行（草稿）
		if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
			event.preventDefault();
			openTestDialog();
		}

		// Ctrl+Shift+T：测试当前选中节点（就近验证单节点）
		if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 't') {
			event.preventDefault();
			if (selectedNodeId.value) {
				openNodeTestDialog(selectedNodeId.value);
			} else {
				ElMessage.warning(t('请先选中要测试的节点'));
			}
		}

		// Ctrl/Cmd+D：复制选中节点（未 preventDefault 时浏览器会弹"添加书签"，必须拦截）
		if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'd') {
			event.preventDefault();
			duplicateSelectedElements();
		}

		if (event.key === 'Delete' || event.key === 'Backspace') {
			const activeEl = document.activeElement;
			const inEditable =
				!!activeEl &&
				(activeEl.tagName === 'INPUT' ||
					activeEl.tagName === 'TEXTAREA' ||
					activeEl.hasAttribute('contenteditable'));
			if (!inEditable) {
				deleteSelectedElements();
			}
		}
	}

	return { handleKeyDown };
}
