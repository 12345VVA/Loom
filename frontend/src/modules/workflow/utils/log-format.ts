/**
 * 工作流日志抽屉的格式化与状态映射纯函数。
 * 自 log-drawer.vue 抽出：全部无副作用；涉及文案翻译的以 t 参数注入
 * （与原实现一致的 locale 快照语义，非响应式）。
 */
import dayjs from 'dayjs';
import type { WorkflowLogItem } from '../utils';

export type TranslateFn = (key: string) => string;

export type TagType = 'success' | 'danger' | 'primary' | 'info' | 'warning';

export function getTimelineType(status?: string): 'success' | 'danger' | 'primary' | 'info' {
	if (status === 'success') return 'success';
	if (status === 'error' || status === 'failed') return 'danger';
	if (status === 'running') return 'primary';
	return 'info';
}

export function getStatusTagType(status?: string): 'success' | 'danger' | 'primary' | 'info' {
	if (status === 'success') return 'success';
	if (status === 'error' || status === 'failed') return 'danger';
	if (status === 'running') return 'primary';
	return 'info';
}

export function getStatusLabel(status: string | undefined, t: TranslateFn): string {
	if (status === 'success') return t('成功');
	if (status === 'error' || status === 'failed') return t('失败');
	if (status === 'running') return t('运行中');
	return status || '-';
}

export function getLatencyTagType(ms?: number): 'success' | 'warning' | 'danger' | 'info' {
	if (!ms) return 'info';
	if (ms > 30000) return 'danger';
	if (ms > 5000) return 'warning';
	return 'info';
}

export function formatLatency(ms?: number): string {
	if (ms === undefined || ms === null || isNaN(ms)) return '-';
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
	const min = Math.floor(ms / 60000);
	const sec = ((ms % 60000) / 1000).toFixed(1);
	return `${min}m ${sec}s`;
}

export function formatTime(value: string | undefined, timeFormat: string): string {
	return value ? dayjs(value).format(timeFormat) : '-';
}

export function formatShortTime(value?: string): string {
	return value ? dayjs(value).format('HH:mm:ss') : '-';
}

export function formatFullTime(value?: string): string {
	return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

/** 异常分类智能推断 */
export function inferErrorCategory(msg: string, t: TranslateFn): string {
	if (!msg) return t('执行异常');
	const lower = msg.toLowerCase();
	if (lower.includes('timeout') || lower.includes('timed out')) return 'TIMEOUT';
	if (lower.includes('connect') || lower.includes('network') || lower.includes('connection'))
		return 'NETWORK';
	if (
		lower.includes('auth') ||
		lower.includes('token') ||
		lower.includes('permission') ||
		lower.includes('401') ||
		lower.includes('403')
	)
		return 'AUTH';
	if (lower.includes('rate') || lower.includes('limit') || lower.includes('429'))
		return 'RATE_LIMIT';
	if (lower.includes('json') || lower.includes('parse') || lower.includes('syntax'))
		return 'SYNTAX';
	if (lower.includes('valid') || lower.includes('schema') || lower.includes('type'))
		return 'VALIDATION';
	return t('运行时异常');
}

/** 辅助检测：是否含有故事或长文案业务结构 */
export function hasStoryOrCopyContent(item: WorkflowLogItem): boolean {
	const str = item.outputData || '';
	return (
		str.includes('copy_text') ||
		str.includes('story_text') ||
		str.includes('paragraphs') ||
		str.includes('paragraphs_array') ||
		str.includes('plan_output')
	);
}

export interface NodeMeta {
	label: string;
	tagType: 'primary' | 'success' | 'warning' | 'info' | 'danger';
	icon: string;
	color: string;
	bg: string;
}

/**
 * 节点专属元数据映射工厂。
 * 原 NODE_META_MAP 在组件 setup 中以 t() 构建一次（locale 快照），
 * 此处保持等价语义：每个组件实例调用一次本工厂。
 */
export function createNodeMetaMap(t: TranslateFn): {
	map: Record<string, NodeMeta>;
	getNodeMeta: (type?: string) => NodeMeta;
} {
	const map: Record<string, NodeMeta> = {
		llm: {
			label: t('大模型'),
			tagType: 'warning',
			icon: 'llm',
			color: '#8b5cf6',
			bg: 'rgba(139, 92, 246, 0.12)'
		},
		image_generator: {
			label: t('图像生成'),
			tagType: 'success',
			icon: 'image_generator',
			color: '#10b981',
			bg: 'rgba(16, 185, 129, 0.12)'
		},
		loop_controller: {
			label: t('循环控制'),
			tagType: 'warning',
			icon: 'loop_controller',
			color: '#f59e0b',
			bg: 'rgba(245, 158, 11, 0.12)'
		},
		variable_transform: {
			label: t('变量转换'),
			tagType: 'info',
			icon: 'variable_transform',
			color: '#0ea5e9',
			bg: 'rgba(14, 165, 233, 0.12)'
		},
		variable_assignment: {
			label: t('变量赋值'),
			tagType: 'info',
			icon: 'variable_assignment',
			color: '#14b8a6',
			bg: 'rgba(20, 184, 166, 0.12)'
		},
		condition: {
			label: t('条件判断'),
			tagType: 'warning',
			icon: 'condition',
			color: '#f97316',
			bg: 'rgba(249, 115, 22, 0.12)'
		},
		switch: {
			label: t('条件分支'),
			tagType: 'warning',
			icon: 'switch',
			color: '#d946ef',
			bg: 'rgba(217, 70, 239, 0.12)'
		},
		tool_executor: {
			label: t('工具执行'),
			tagType: 'primary',
			icon: 'tool_executor',
			color: '#3b82f6',
			bg: 'rgba(59, 130, 246, 0.12)'
		},
		tool: {
			label: t('工具执行'),
			tagType: 'primary',
			icon: 'tool_executor',
			color: '#3b82f6',
			bg: 'rgba(59, 130, 246, 0.12)'
		},
		human_input: {
			label: t('人工确认'),
			tagType: 'danger',
			icon: 'human_input',
			color: '#f43f5e',
			bg: 'rgba(244, 63, 94, 0.12)'
		},
		intent_classifier: {
			label: t('意图分类'),
			tagType: 'primary',
			icon: 'intent_classifier',
			color: '#6366f1',
			bg: 'rgba(99, 102, 241, 0.12)'
		},
		start: {
			label: t('开始节点'),
			tagType: 'success',
			icon: 'start',
			color: '#22c55e',
			bg: 'rgba(34, 197, 94, 0.12)'
		},
		end: {
			label: t('结束节点'),
			tagType: 'info',
			icon: 'end',
			color: '#64748b',
			bg: 'rgba(100, 116, 139, 0.12)'
		},
		batch_processor: {
			label: t('批处理器'),
			tagType: 'primary',
			icon: 'batch_processor',
			color: '#06b6d4',
			bg: 'rgba(6, 182, 212, 0.12)'
		}
	};

	function getNodeMeta(type?: string): NodeMeta {
		if (!type || !map[type]) {
			return {
				label: type || t('步骤'),
				tagType: 'info',
				icon: 'default',
				color: '#64748b',
				bg: 'rgba(100, 116, 139, 0.12)'
			};
		}
		return map[type];
	}

	return { map, getNodeMeta };
}
