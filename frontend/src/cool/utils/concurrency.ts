/**
 * 并发闸门（异步审查 P2-3）：FIFO 排队 + 并发计数上限。
 *
 * 用于 axios adapter 层做全站请求并发上限，防止资产列表等场景同时打
 * 几十个请求压爆后端连接池。独立成工具便于 vitest 直测。
 */
export function createGate(limit: number) {
	const max = Math.max(1, Math.floor(limit));
	let active = 0;
	const waiters: Array<() => void> = [];

	async function acquire(): Promise<void> {
		while (active >= max) {
			await new Promise<void>(resolve => waiters.push(resolve));
		}
		active += 1;
	}

	function release(): void {
		active = Math.max(0, active - 1);
		waiters.shift()?.();
	}

	return {
		get activeCount() {
			return active;
		},
		async run<TResult>(fn: () => Promise<TResult>): Promise<TResult> {
			await acquire();
			try {
				return await fn();
			} finally {
				release();
			}
		}
	};
}
