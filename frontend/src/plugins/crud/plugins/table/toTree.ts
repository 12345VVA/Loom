import { useCrud } from '@cool-vue/crud';
import { deepTree } from '/@/cool/utils';
import { isEmpty } from 'lodash-es';

interface Item extends Eps.BaseSysMenuEntity {
	children?: Item[];
	_children?: Item[];
	hasChildren?: boolean;
}

/** cl-table 组件实例中本插件触达的最小面（类型化过渡，深链待 crud 包类型化收敛） */
interface ToTreeExposed {
	Table: {
		value: {
			store: {
				loadOrToggle: (row: Item) => void;
				states: { lazyTreeNodeMap: { value: { [key: number]: Item[] } } };
			};
		};
	};
	config: { props: Record<string, unknown>; on: Record<string, unknown> };
}

/**
 * 树形表格
 * @param options.lazy 是否懒加载，数据过多时开启
 * @param options.onRefresh 刷新方法
 * @returns
 */
export function toTree(
	options: { lazy?: boolean; onRefresh?: (params: any) => Promise<any[]> } = {}
) {
	return ({ exposed }: { exposed: unknown }) => {
		const t = exposed as ToTreeExposed;
		const Crud = useCrud();

		// 设置刷新方法
		if (Crud.value) {
			// 原 cl-crud 的 onRefresh
			const onRefresh = Crud.value.config.onRefresh;

			// 重写 onRefresh
			Crud.value.config.onRefresh = async (
				params: Parameters<ClCrud.Config['onRefresh']>[0],
				{ render, next, done }: Parameters<ClCrud.Config['onRefresh']>[1]
			) => {
				const req: Promise<any[]> = new Promise(resolve => {
					if (onRefresh) {
						const _next = async (params?: any) => {
							const res = await next(params);
							resolve(res.list);
						};

						const _render = (list: any[]) => {
							resolve(list);
						};

						onRefresh(params, { render: _render, next: _next, done });
					} else {
						resolve(
							options.onRefresh
								? options.onRefresh(params)
								: Crud.value?.service[Crud.value.dict.api.list](params)
						);
					}
				});

				const list = await req;

				render(onData(list, params.sort));
			};
		}

		// 数据处理
		const onData = (list: Item[], sort: 'desc' | 'asc') => {
			const data = deepTree(list, sort);

			// 递归处理
			const deep = (arr: Item[]) => {
				arr.forEach(e => {
					const nodes: { [key: number]: Item[] } =
						t.Table.value?.store.states.lazyTreeNodeMap.value || {};

					if (nodes[e.id!]) {
						nodes[e.id!] = e.children || [];
					}

					if (!isEmpty(e.children)) {
						e.hasChildren = true;
						e._children = e.children;

						if (options.lazy) {
							delete e.children;
						}

						deep(e._children || []);
					}
				});
			};

			deep(data);

			return data;
		};

		// 层级参数
		t.config.props.lazy = true;
		t.config.props['row-key'] = 'id';
		t.config.props['tree-props'] = {
			children: 'children',
			hasChildren: 'hasChildren'
		};

		// 层级事件
		t.config.on.load = (
			row: Item,
			treeNode: unknown,
			resolve: (data: Item[]) => void
		) => {
			resolve(row._children || []);
		};

		// 行点击
		t.config.on.onRowClick = (row: Item) => {
			if (row._children) {
				t.Table.value?.store.loadOrToggle(row);
			}
		};
	};
}
