/**
 * 计划任务列表动作（从 views/list.vue 拆出）。
 *
 * 封装刷新、带确认框的启停删操作与"执行一次"；service 依赖由调用方注入，
 * 便于单测替换。
 */
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';

/** 动作函数关心的最小字段面（实体类型由调用方以泛型传入，保持 EPS 类型自洽）。 */
export interface TaskActionItem {
	id?: number;
	name?: string;
	type?: number;
	status?: number | boolean;
	every?: number;
	/** 列表展示用的秒级间隔（存库值为毫秒，refresh 内换算） */
	_every?: number;
	[key: string]: unknown;
}

export interface TaskInfoService {
	page: (req: unknown) => Promise<{ list: TaskActionItem[] }>;
	start: (req: unknown) => Promise<unknown>;
	stop: (req: unknown) => Promise<unknown>;
	delete: (req: unknown) => Promise<unknown>;
	once: (req: unknown) => Promise<unknown>;
}

export type TranslateFn = (key: string, named?: Record<string, unknown>) => string;

export function useTaskActions<T extends TaskActionItem = TaskActionItem>(
	service: TaskInfoService,
	t: TranslateFn
) {
	const list = ref<T[]>([]);

	/** 拉取任务列表；every 存库毫秒 → 交互秒（_every 供展示）。 */
	function refresh() {
		return service.page({ size: 100, page: 1 }).then(res => {
			list.value = res.list.map(e => {
				if (e.every) {
					e._every = parseInt(String(e.every / 1000));
				}
				return e;
			}) as T[];
		});
	}

	/** 统一操作处理器：确认框 → 执行 → 成功提示 + 刷新；取消静默、失败提示。 */
	async function handleAction(item: T, actionName: string, run: () => Promise<unknown>) {
		try {
			await ElMessageBox.confirm(
				t('此操作将{action}任务（{name}），是否继续？', {
					action: actionName,
					name: item.name as string
				}),
				t('提示'),
				{
					type: 'warning'
				}
			);
			await run();
			ElMessage.success(t('{action}成功', { action: actionName }));
			refresh();
		} catch (err) {
			if (err !== 'cancel') {
				// service 层抛出的错误对象未必是 Error 实例，按鸭子类型取 message
				const message = (err as { message?: string } | null | undefined)?.message || t('操作失败');
				ElMessage.error(message);
			}
		}
	}

	// 启用任务
	function start(item: T) {
		handleAction(item, t('启用'), () => service.start({ id: item.id, type: item.type }));
	}

	// 停用任务
	function stop(item: T) {
		handleAction(item, t('停用'), () => service.stop({ id: item.id }));
	}

	// 删除任务
	function remove(item: T) {
		handleAction(item, t('删除'), () => service.delete({ ids: [item.id] }));
	}

	// 执行一次（返回 promise 便于测试确定性等待；调用方 fire-and-forget 不受影响）
	function once(item: T): Promise<void> {
		return service
			.once({ id: item.id })
			.then(() => {
				refresh();
			})
			.catch((err: Error) => {
				ElMessage.error(err.message);
			});
	}

	return {
		list,
		refresh,
		handleAction,
		start,
		stop,
		remove,
		once
	};
}
