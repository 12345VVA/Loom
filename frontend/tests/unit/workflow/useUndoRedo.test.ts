import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { useUndoRedo } from '/$/workflow/composables/useUndoRedo';

describe('useUndoRedo', () => {
	it('round-trips element state through undo/redo', () => {
		const elements = ref<any[]>([{ id: 'a' }]);
		const { init, pushSnapshot, undo, redo, canUndo } = useUndoRedo(elements);
		init();

		elements.value.push({ id: 'b' });
		pushSnapshot();
		expect(canUndo.value).toBe(true);

		expect(undo()).toBe(true);
		expect(elements.value).toHaveLength(1);
		expect(elements.value[0].id).toBe('a');

		expect(redo()).toBe(true);
		expect(elements.value).toHaveLength(2);
	});

	it('truncates the redo stack when a new snapshot is pushed after undo', () => {
		const elements = ref<any[]>([{ id: 'a' }]);
		const { init, pushSnapshot, undo, redo, canRedo } = useUndoRedo(elements);
		init();
		elements.value.push({ id: 'b' });
		pushSnapshot();
		undo();
		expect(canRedo.value).toBe(true);

		// 新快照应清空 redo 栈（标准 UndoManager 语义）
		elements.value.push({ id: 'c' });
		pushSnapshot();
		expect(canRedo.value).toBe(false);
	});

	// [P1 回归] elements 含 Vue 组件引用/函数时 structuredClone 会抛 DataCloneError，
	// deepClone 必须回退 JSON，否则 undo/redo 崩溃
	it('does not throw when elements contain non-cloneable values (functions/component refs)', () => {
		const elements = ref<any[]>([{ id: 'a', icon: () => {} }]);
		const { init, pushSnapshot, undo } = useUndoRedo(elements);
		expect(() => {
			init();
			elements.value.push({ id: 'b' });
			pushSnapshot();
			undo();
		}).not.toThrow();
		expect(elements.value).toHaveLength(1);
	});

	it('preserves the timestamp value through undo (clone mechanism is env-dependent)', () => {
		const d = new Date(2020, 0, 1);
		const elements = ref<any[]>([{ id: 'a', at: d }]);
		const { init, pushSnapshot, undo } = useUndoRedo(elements);
		init();
		elements.value = [{ id: 'b' }];
		pushSnapshot();
		undo();
		// 生产环境(浏览器 structuredClone)保留 Date 实例；测试环境(jsdom 无 structuredClone)回退 JSON 得 ISO 字符串
		const restored = elements.value[0].at;
		const ts = restored instanceof Date ? restored.getTime() : new Date(restored).getTime();
		expect(ts).toBe(d.getTime());
	});
});
