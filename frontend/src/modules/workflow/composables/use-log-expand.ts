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
	const activeTabs = reactive<Record<string, string>>({});

	// 稳定 key（WFU-M21）：无 id 项此前用全量列表下标，筛选后模板绑定的筛选下标
	// 与初始化写入的下标不是同一个——Tab 选中错位/空；nodeId 是日志行天然稳定标识
	function tabKeyOf(item: WorkflowLogItem): string {
		return String(item.id ?? item.nodeId ?? '');
	}

	// 初始化每个步骤选中的 Tab（智能结果优先）
	watch(
		() => items.value,
		list => {
			list.forEach(item => {
				const key = tabKeyOf(item);
				if (key && !activeTabs[key]) {
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
