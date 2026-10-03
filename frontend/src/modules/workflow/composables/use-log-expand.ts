/**
 * 工作流日志抽屉的展开/Tab 态。
 * 自 log-drawer.vue 抽出：卡片 Tab 选中态、全部展开/收起/仅异常。
 * expand-all / collapse-all 的对外 emit 由组件层以回调注入。
 */
import { reactive, watch, type Ref } from 'vue';
import type { WorkflowLogItem } from '../utils';

export function useLogExpand(options: {
	items: Ref<WorkflowLogItem[]>;
	getInitialActiveTab: (item: WorkflowLogItem) => string;
	onExpandAll: () => void;
	onCollapseAll: () => void;
}) {
	const { items, getInitialActiveTab, onExpandAll, onCollapseAll } = options;

	// 每个卡片当前选中的 tab 名
	const activeTabs = reactive<Record<string | number, string>>({});

	// 初始化每个步骤选中的 Tab（智能结果优先）
	watch(
		() => items.value,
		list => {
			list.forEach((item, index) => {
				const key = item.id || index;
				if (!activeTabs[key]) {
					activeTabs[key] = getInitialActiveTab(item);
				}
			});
		},
		{ immediate: true, deep: true }
	);

	function toggleExpand(item: WorkflowLogItem) {
		item.isExpanded = !item.isExpanded;
	}

	function handleExpandAll() {
		items.value.forEach(i => (i.isExpanded = true));
		onExpandAll();
	}

	function handleCollapseAll() {
		items.value.forEach(i => (i.isExpanded = false));
		onCollapseAll();
	}

	function handleExpandErrorsOnly() {
		items.value.forEach(i => {
			i.isExpanded = i.status === 'error' || i.status === 'failed';
		});
	}

	return { activeTabs, toggleExpand, handleExpandAll, handleCollapseAll, handleExpandErrorsOnly };
}
