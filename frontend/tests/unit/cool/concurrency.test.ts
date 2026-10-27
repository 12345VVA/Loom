import { describe, expect, it, vi } from 'vitest';
import { createGate } from '../../../src/cool/utils/concurrency';

describe('createGate（异步审查 P2-3 并发闸门）', () => {
	it('并发数不超过 limit，全部任务完成', async () => {
		const gate = createGate(2);
		let peak = 0;
		let active = 0;

		const tasks = Array.from({ length: 5 }, () =>
			gate.run(async () => {
				active += 1;
				peak = Math.max(peak, active);
				await new Promise(resolve => setTimeout(resolve, 10));
				active -= 1;
				return 'ok';
			})
		);

		const results = await Promise.all(tasks);
		expect(results).toEqual(['ok', 'ok', 'ok', 'ok', 'ok']);
		expect(peak).toBeLessThanOrEqual(2);
	});

	it('FIFO：排队任务按进入顺序执行', async () => {
		const gate = createGate(1);
		const order: number[] = [];

		const tasks = [1, 2, 3].map(n => gate.run(async () => order.push(n)));
		await Promise.all(tasks);
		expect(order).toEqual([1, 2, 3]);
	});

	it('任务异常也释放槽位，后续任务可执行', async () => {
		const gate = createGate(1);
		await expect(gate.run(async () => Promise.reject(new Error('boom')))).rejects.toThrow('boom');

		const result = await gate.run(async () => 'recovered');
		expect(result).toBe('recovered');
	});

	it('limit=0 下限保护为 1，不会死锁', async () => {
		const gate = createGate(0);
		const result = await gate.run(async () => 'ok');
		expect(result).toBe('ok');
	});

	it('拒绝路径不影响 waiters 唤醒（vi 防回归：release 必在 finally）', async () => {
		const gate = createGate(1);
		const spy = vi.fn();
		const first = gate.run(async () => {
			await new Promise(resolve => setTimeout(resolve, 5));
			throw new Error('first fails');
		});
		const second = gate.run(async () => {
			spy();
			return 'second';
		});
		await expect(first).rejects.toThrow('first fails');
		await expect(second).resolves.toBe('second');
		expect(spy).toHaveBeenCalledTimes(1);
	});
});
