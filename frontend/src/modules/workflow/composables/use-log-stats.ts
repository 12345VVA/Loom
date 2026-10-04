/**
 * 工作流日志统计指标与运行摘要（从 log-drawer.vue 拆出）。
 *
 * 输入均为 getter（兼容 ref/computed/字面量），统计 computed 随 items 变化；
 * buildRunSummary 为纯函数，便于单测断言摘要文本格式。
 */
import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import type { WorkflowLogItem } from '../utils';
import { formatLatency, type TranslateFn } from '../utils/log-format';

export interface LogStatsInput {
	items: MaybeRefOrGetter<WorkflowLogItem[]>;
	/** 顶部运行状态（editor 测试运行用），缺省视为准备中 */
	status?: MaybeRefOrGetter<string | undefined>;
	title?: MaybeRefOrGetter<string>;
	/** 图片产物数（来自 useLogImages 的全量图片清单） */
	imageCount?: MaybeRefOrGetter<number>;
	t: TranslateFn;
}

/** 构建"复制执行摘要"的纯文本（格式与剪贴板内容一致）。 */
export function buildRunSummary(input: {
	title: string;
	total: number;
	success: number;
	fail: number;
	totalTime: string;
	llm: number;
	tool: number;
	images: number;
	statusText: string;
	t: TranslateFn;
}): string {
	const { t } = input;
	let summary = `【${input.title || t('工作流执行摘要')}】\n`;
	summary += `· ${t('步骤总数')}：${input.total}（${t('成功')} ${input.success}，${t('失败')} ${input.fail}）\n`;
	summary += `· ${t('总耗时')}：${input.totalTime}\n`;
	summary += `· ${t('大模型调用')}：${input.llm} ${t('次')}\n`;
	if (input.tool > 0) summary += `· ${t('工具调用')}：${input.tool} ${t('次')}\n`;
	if (input.images > 0) summary += `· ${t('图片产物')}：${input.images} ${t('张')}\n`;
	summary += `· ${t('执行状态')}：${input.statusText}\n`;
	return summary;
}

export function useLogStats(options: LogStatsInput) {
	const { t } = options;

	const successCount = computed(() => {
		return toValue(options.items).filter(i => i.status === 'success').length;
	});

	const failCount = computed(() => {
		return toValue(options.items).filter(i => i.status === 'error' || i.status === 'failed').length;
	});

	const totalLatencyMs = computed(() => {
		return toValue(options.items).reduce((acc, cur) => acc + (cur.latencyMs || 0), 0);
	});

	// AI 运行时关键观测指标：大模型调用总数与工具执行总数
	const llmCount = computed(() => {
		return toValue(options.items).filter(i => i.nodeType === 'llm').length;
	});

	const toolCount = computed(() => {
		return toValue(options.items).filter(
			i => i.nodeType === 'tool' || i.nodeType === 'tool_executor' || i.nodeType === 'batch_processor'
		).length;
	});

	const statusTagType = computed<'success' | 'danger' | 'primary' | 'warning'>(() => {
		const status = toValue(options.status);
		if (status === 'success') return 'success';
		if (status === 'failed' || status === 'error') return 'danger';
		if (status === 'paused') return 'warning';
		return 'primary';
	});

	const statusLabel = computed(() => {
		const status = toValue(options.status);
		if (!status) return t('准备中');
		const map: Record<string, string> = {
			pending: t('待运行'),
			running: t('运行中'),
			paused: t('已挂起'),
			success: t('成功'),
			failed: t('失败')
		};
		return map[status] || status;
	});

	/** 执行摘要文案（剪贴板内容由组件层负责写入）。 */
	function buildSummaryText(): string {
		const status = toValue(options.status);
		const fail = failCount.value;
		return buildRunSummary({
			title: toValue(options.title) || '',
			total: toValue(options.items).length,
			success: successCount.value,
			fail,
			totalTime: formatLatency(totalLatencyMs.value),
			llm: llmCount.value,
			tool: toolCount.value,
			images: toValue(options.imageCount) ?? 0,
			statusText: status || (fail > 0 ? t('失败') : t('成功')),
			t
		});
	}

	return {
		successCount,
		failCount,
		totalLatencyMs,
		llmCount,
		toolCount,
		statusTagType,
		statusLabel,
		buildSummaryText
	};
}
