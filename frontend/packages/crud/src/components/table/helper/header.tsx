import { CloseBold, Search } from "@element-plus/icons-vue";
import { h } from "vue";
import { useCrud } from "../../../hooks";
import { renderNode } from "../../../utils/vnode";

export function renderHeader(item: ClTable.Column, { scope, slots }: any) {
	const crud = useCrud();

	const slot = slots[`header-${item.prop}`];

	if (slot) {
		return slot({
			scope
		});
	}

	if (!item.search || !item.search.component) {
		return item.label;
	}

	// 显示输入框
	function show(e: MouseEvent) {
		item.search.isInput = true;
		e.stopPropagation();
	}

	// 隐藏输入框
	function hide() {
		if (item.search.value !== undefined) {
			item.search.value = undefined;
			refresh();
		}

		item.search.isInput = false;
	}

	// 刷新
	function refresh(params?: any) {
		const { value } = item.search;

		crud.value?.refresh({
			page: 1,
			[item.prop]: value === "" ? undefined : value,
			...params
		});
	}

	// 文字
	const text = (
		<div class="cl-table-header__search-label" onClick={show}>
			<el-icon size={14}>{item.search.icon?.() ?? <Search />}</el-icon>

			{item.renderLabel ? item.renderLabel(scope) : item.label}
		</div>
	);

	// 输入框
	const input = h(renderNode(item.search.component, { prop: item.prop }), {
		clearable: true,
		modelValue: item.search.value,
		onVnodeMounted(vn) {
			// 默认聚焦
			vn.component?.exposed?.focus?.();
		},
		onInput(val: any) {
			item.search.value = val;
		},
		onChange(val: any) {
			item.search.value = val;

			// 更改时刷新列表
			if (item.search.refreshOnChange) {
				refresh();
			}
		}
	});

	return (
		<div class={["cl-table-header__search", { "is-input": item.search.isInput }]}>
			<div class="cl-table-header__search-inner">{item.search.isInput ? input : text}</div>

			{item.search.isInput && (
				<div class="cl-table-header__search-close" onClick={hide}>
					<el-icon>
						<CloseBold />
					</el-icon>
				</div>
			)}
		</div>
	);
}
