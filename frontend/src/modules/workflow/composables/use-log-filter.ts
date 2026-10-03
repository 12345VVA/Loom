/**
 * 工作流日志抽屉的筛选状态。
 * 自 log-drawer.vue 抽出：状态筛选 + 关键词模糊匹配。
 */
import { computed, ref, type Ref } from 'vue';
import type { WorkflowLogItem } from '../utils';

export function useLogFilter(options: {
	items: Ref<WorkflowLogItem[]>;
	hasDetectedImages: (item: WorkflowLogItem) => boolean;
}) {
	const { items, hasDetectedImages } = options;

	const searchKeyword = ref('');
	const filterStatus = ref<'all' | 'success' | 'error' | 'media'>('all');

	// 筛选后的列表
	const filteredItems = computed(() => {
		let list = items.value;

		// 1. 状态筛选
		if (filterStatus.value === 'success') {
			list = list.filter(i => i.status === 'success');
		} else if (filterStatus.value === 'error') {
			list = list.filter(i => i.status === 'error' || i.status === 'failed');
		} else if (filterStatus.value === 'media') {
			list = list.filter(i => hasDetectedImages(i));
		}

		// 2. 关键词模糊匹配
		const kw = searchKeyword.value.trim().toLowerCase();
		if (kw) {
			list = list.filter(item => {
				return (
					(item.nodeName && item.nodeName.toLowerCase().includes(kw)) ||
					(item.nodeId && item.nodeId.toLowerCase().includes(kw)) ||
					(item.nodeType && item.nodeType.toLowerCase().includes(kw)) ||
					(item.errorMessage && item.errorMessage.toLowerCase().includes(kw))
				);
			});
		}

		return list;
	});

	return { searchKeyword, filterStatus, filteredItems };
}
