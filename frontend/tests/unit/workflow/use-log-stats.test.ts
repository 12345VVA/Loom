import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { buildRunSummary, useLogStats } from '/$/workflow/composables/use-log-stats';
import type { WorkflowLogItem } from '/$/workflow/utils';

const t = (key: string) => key;

function logItem(partial: Partial<WorkflowLogItem>): WorkflowLogItem {
	return {
		id: Math.random(),
		title: 'step',
		status: 'success',
		...partial
	} as WorkflowLogItem;
}

describe('workflow use-log-stats', () => {
	it('counts success/failure, latency, llm and tool calls', () => {
		const items = [
			logItem({ status: 'success', latencyMs: 100, nodeType: 'llm' }),
			logItem({ status: 'error', latencyMs: 50, nodeType: 'tool' }),
			logItem({ status: 'failed', latencyMs: undefined, nodeType: 'tool_executor' }),
			logItem({ status: 'success', latencyMs: 30, nodeType: 'batch_processor' }),
			logItem({ status: 'running', latencyMs: 20, nodeType: 'start' })
		];
		const stats = useLogStats({ items: ref(items), t });
		expect(stats.successCount.value).toBe(2);
		expect(stats.failCount.value).toBe(2);
		expect(stats.totalLatencyMs.value).toBe(200);
		expect(stats.llmCount.value).toBe(1);
		// tool / tool_executor / batch_processor 都计为工具调用
		expect(stats.toolCount.value).toBe(3);
	});

	it('maps run status to tag type and label with fallbacks', () => {
		const status = ref<string | undefined>(undefined);
		const stats = useLogStats({ items: ref([]), status, t });
		expect(stats.statusTagType.value).toBe('primary');
		expect(stats.statusLabel.value).toBe('准备中');

		status.value = 'success';
		expect(stats.statusTagType.value).toBe('success');
		expect(stats.statusLabel.value).toBe('成功');

		status.value = 'failed';
		expect(stats.statusTagType.value).toBe('danger');
		expect(stats.statusLabel.value).toBe('失败');

		status.value = 'paused';
		expect(stats.statusTagType.value).toBe('warning');
		expect(stats.statusLabel.value).toBe('已挂起');

		status.value = 'custom-state';
		expect(stats.statusLabel.value).toBe('custom-state');
	});

	it('builds run summary text with tool/image sections only when present', () => {
		const text = buildRunSummary({
			title: '我的工作流',
			total: 3,
			success: 2,
			fail: 1,
			totalTime: '1.2s',
			llm: 2,
			tool: 0,
			images: 0,
			statusText: '失败',
			t
		});
		expect(text).toContain('【我的工作流】');
		expect(text).toContain('· 步骤总数：3（成功 2，失败 1）');
		expect(text).toContain('· 总耗时：1.2s');
		expect(text).toContain('· 大模型调用：2 次');
		expect(text).toContain('· 执行状态：失败');
		expect(text).not.toContain('工具调用');
		expect(text).not.toContain('图片产物');

		const withExtras = buildRunSummary({
			title: '',
			total: 1,
			success: 1,
			fail: 0,
			totalTime: '0.5s',
			llm: 0,
			tool: 1,
			images: 4,
			statusText: '成功',
			t
		});
		// 标题为空时回退默认名
		expect(withExtras).toContain('【工作流执行摘要】');
		expect(withExtras).toContain('· 工具调用：1 次');
		expect(withExtras).toContain('· 图片产物：4 张');
	});
});
