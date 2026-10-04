import { describe, expect, it, vi, beforeEach } from 'vitest';

// ElMessage/ElMessageBox 以 mock 注入，断言提示与确认流
vi.mock('element-plus', () => {
	return {
		ElMessage: {
			success: vi.fn(),
			error: vi.fn(),
			warning: vi.fn()
		},
		ElMessageBox: {
			confirm: vi.fn()
		}
	};
});

import { ElMessage, ElMessageBox } from 'element-plus';
import { useTaskActions, type TaskInfoService } from '/$/task/composables/use-task-actions';

const t = (key: string, named?: Record<string, unknown>) =>
	named ? `${key}:${JSON.stringify(named)}` : key;

function makeService(): TaskInfoService & { page: ReturnType<typeof vi.fn> } {
	return {
		page: vi.fn().mockResolvedValue({
			list: [
				{ id: 1, name: 'demo', every: 60000 },
				{ id: 2, name: 'once', every: 0 }
			]
		}),
		start: vi.fn().mockResolvedValue(undefined),
		stop: vi.fn().mockResolvedValue(undefined),
		delete: vi.fn().mockResolvedValue(undefined),
		once: vi.fn().mockResolvedValue(undefined)
	} as never;
}

const item = { id: 1, name: 'demo', type: 0, status: true };

beforeEach(() => {
	vi.clearAllMocks();
});

describe('task use-task-actions', () => {
	it('refresh loads list and converts every ms to seconds', async () => {
		const service = makeService();
		const { list, refresh } = useTaskActions(service, t);
		await refresh();
		expect(service.page).toHaveBeenCalledWith({ size: 100, page: 1 });
		expect(list.value).toHaveLength(2);
		expect(list.value[0]._every).toBe(60);
		// every 为 0 时不做换算
		expect(list.value[1]._every).toBeUndefined();
	});

	it('handleAction: confirm → run → success toast → refresh', async () => {
		vi.mocked(ElMessageBox.confirm).mockResolvedValue(undefined);
		const service = makeService();
		const { handleAction, refresh } = useTaskActions(service, t);
		const run = vi.fn().mockResolvedValue(undefined);
		await handleAction(item, '启用', run);
		expect(ElMessageBox.confirm).toHaveBeenCalledWith(
			expect.stringContaining('"name":"demo"'),
			'提示',
			{ type: 'warning' }
		);
		expect(run).toHaveBeenCalled();
		expect(ElMessage.success).toHaveBeenCalled();
		expect(service.page).toHaveBeenCalled();
		expect(refresh).toBeTruthy();
	});

	it('handleAction: cancel is silent, failure shows error message', async () => {
		vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel');
		const service = makeService();
		const { handleAction } = useTaskActions(service, t);
		await handleAction(item, '删除', vi.fn());
		expect(ElMessage.error).not.toHaveBeenCalled();

		vi.mocked(ElMessageBox.confirm).mockResolvedValueOnce(undefined);
		await handleAction(item, '删除', vi.fn().mockRejectedValue({ message: 'boom' }));
		expect(ElMessage.error).toHaveBeenCalledWith('boom');
		expect(service.delete).not.toHaveBeenCalled();
	});

	it('start/stop/remove route to corresponding service calls', async () => {
		vi.mocked(ElMessageBox.confirm).mockResolvedValue(undefined);
		const service = makeService();
		const { start, stop, remove } = useTaskActions(service, t);

		await start(item);
		expect(service.start).toHaveBeenCalledWith({ id: 1, type: 0 });

		await stop(item);
		expect(service.stop).toHaveBeenCalledWith({ id: 1 });

		await remove(item);
		expect(service.delete).toHaveBeenCalledWith({ ids: [1] });
	});

	it('once triggers service.once and refreshes without confirm', async () => {
		const service = makeService();
		const { once } = useTaskActions(service, t);
		await once(item);
		expect(service.once).toHaveBeenCalledWith({ id: 1 });
		expect(service.page).toHaveBeenCalled();
	});

	it('once failure surfaces error message', async () => {
		const service = makeService();
		service.once = vi.fn().mockRejectedValue(new Error('nope'));
		const { once } = useTaskActions(service, t);
		// once 返回 promise（catch 已在内部消化），await 后断言确定性成立
		await once(item);
		expect(ElMessage.error).toHaveBeenCalledWith('nope');
	});
});
