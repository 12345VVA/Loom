import { describe, expect, it } from 'vitest';
import { ref, computed } from 'vue';
import { useContextMenu } from '/$/workflow/composables/useContextMenu';
import { UNTESTABLE_NODE_TYPES } from '/$/workflow/components/constants';

describe('useContextMenu', () => {
	const emptySelection = computed(() => []);

	describe('canTestContextNode', () => {
		it('nodeId 为空时为 false', () => {
			const elements = ref<any[]>([]);
			const { canTestContextNode } = useContextMenu(elements, emptySelection);
			expect(canTestContextNode.value).toBe(false);
		});

		it('不可测试的节点类型（UNTESTABLE_NODE_TYPES）为 false', () => {
			const untestableType = UNTESTABLE_NODE_TYPES[0];
			const elements = ref<any[]>([{ id: 'n1', type: untestableType }]);
			const { canTestContextNode, openContextMenu } = useContextMenu(elements, emptySelection);
			openContextMenu('n1', 100, 100);
			expect(canTestContextNode.value).toBe(false);
		});

		it('llm 节点为 true（可测试）', () => {
			expect(UNTESTABLE_NODE_TYPES).not.toContain('llm');
			const elements = ref<any[]>([{ id: 'l1', type: 'llm' }]);
			const { canTestContextNode, openContextMenu } = useContextMenu(elements, emptySelection);
			openContextMenu('l1', 100, 100);
			expect(canTestContextNode.value).toBe(true);
		});

		it('节点不存在时为 false', () => {
			const elements = ref<any[]>([]);
			const { canTestContextNode, openContextMenu } = useContextMenu(elements, emptySelection);
			openContextMenu('missing', 100, 100);
			expect(canTestContextNode.value).toBe(false);
		});
	});

	describe('canDistribute', () => {
		it('选中 < 3 时为 false', () => {
			const elements = ref<any[]>([]);
			const selected = computed(() => [1, 2]);
			const { canDistribute } = useContextMenu(elements, selected);
			expect(canDistribute.value).toBe(false);
		});

		it('选中 >= 3 时为 true', () => {
			const elements = ref<any[]>([]);
			const selected = computed(() => [1, 2, 3]);
			const { canDistribute } = useContextMenu(elements, selected);
			expect(canDistribute.value).toBe(true);
		});
	});

	describe('openContextMenu / closeContextMenu', () => {
		it('openContextMenu 设置 visible、位置与 nodeId', () => {
			const elements = ref<any[]>([{ id: 'l1', type: 'llm' }]);
			const { contextMenu, openContextMenu } = useContextMenu(elements, emptySelection);
			openContextMenu('l1', 100, 100);
			expect(contextMenu.visible).toBe(true);
			expect(contextMenu.nodeId).toBe('l1');
			expect(contextMenu.x).toBe(100);
			expect(contextMenu.y).toBe(100);
		});

		it('closeContextMenu 清空 visible 与 nodeId', () => {
			const elements = ref<any[]>([{ id: 'l1', type: 'llm' }]);
			const { contextMenu, openContextMenu, closeContextMenu } = useContextMenu(
				elements,
				emptySelection
			);
			openContextMenu('l1', 100, 100);
			closeContextMenu();
			expect(contextMenu.visible).toBe(false);
			expect(contextMenu.nodeId).toBe('');
		});

		it('clampMenuPosition：靠近右下边界时向左/上回弹', () => {
			const elements = ref<any[]>([]);
			const { contextMenu, openContextMenu } = useContextMenu(elements, emptySelection);
			// jsdom 视口默认 1024x768；靠近右下角应回弹 menuW/menuH（180）
			openContextMenu('x', window.innerWidth - 10, window.innerHeight - 10);
			expect(contextMenu.x).toBe(window.innerWidth - 10 - 180);
			expect(contextMenu.y).toBe(window.innerHeight - 10 - 180);
		});

		it('clampMenuPosition：远离边界时位置不变', () => {
			const elements = ref<any[]>([]);
			const { contextMenu, openContextMenu } = useContextMenu(elements, emptySelection);
			openContextMenu('x', 100, 100);
			expect(contextMenu.x).toBe(100);
			expect(contextMenu.y).toBe(100);
		});
	});
});
