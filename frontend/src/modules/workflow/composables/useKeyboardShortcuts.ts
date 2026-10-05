import { type Ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router';

/**
 * 编辑器键盘快捷键与路由守卫 composable
 * Esc 关闭面板/菜单、Ctrl+S 保存、Ctrl+Z/Shift+Z 撤销/重做、Delete/Backspace 删除选中元素、
 * Ctrl/Cmd+Enter 试运行、Ctrl+Shift+T 测试选中节点；
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
		// 如果用户正在输入框/文本域中打字，则忽略快捷键删除
		const activeEl = document.activeElement;
		if (
			activeEl &&
			(activeEl.tagName === 'INPUT' ||
				activeEl.tagName === 'TEXTAREA' ||
				activeEl.hasAttribute('contenteditable'))
		) {
			return;
		}

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

		if (event.key === 'Delete' || event.key === 'Backspace') {
			deleteSelectedElements();
		}
	}

	return { handleKeyDown };
}
