import { TableInstance } from 'element-plus';
export declare function useTable(props: any): {
    Table: import('vue').Ref<TableInstance, TableInstance>;
    config: {
        columns: {
            [x: string]: any;
            type: ClTable.ColumnType;
            hidden: boolean | {
                value: boolean;
            };
            component: {
                [x: string]: any;
                name?: string;
                options?: {
                    [x: string]: any;
                    label?: string;
                    value?: any;
                    color?: string;
                    type?: string;
                }[] | {
                    value: {
                        [x: string]: any;
                        label?: string;
                        value?: any;
                        color?: string;
                        type?: string;
                    }[];
                };
                props?: {
                    [x: string]: any;
                    onChange?: (value: any) => void;
                } | {
                    value: {
                        [x: string]: any;
                        onChange?: (value: any) => void;
                    };
                };
                style?: obj;
                slots?: {
                    [key: string]: (data?: any) => any;
                };
                vm?: any;
            };
            search: {
                isInput: boolean;
                value: any;
                icon: () => any;
                refreshOnChange: boolean;
                component: {
                    [x: string]: any;
                    name?: string;
                    options?: {
                        [x: string]: any;
                        label?: string;
                        value?: any;
                        color?: string;
                        type?: string;
                    }[] | {
                        value: {
                            [x: string]: any;
                            label?: string;
                            value?: any;
                            color?: string;
                            type?: string;
                        }[];
                    };
                    props?: {
                        [x: string]: any;
                        onChange?: (value: any) => void;
                    } | {
                        value: {
                            [x: string]: any;
                            onChange?: (value: any) => void;
                        };
                    };
                    style?: obj;
                    slots?: {
                        [key: string]: (data?: any) => any;
                    };
                    vm?: any;
                };
            };
            dict: {
                [x: string]: any;
                label?: string;
                value?: any;
                color?: string;
                type?: string;
            }[] | {
                value: {
                    [x: string]: any;
                    label?: string;
                    value?: any;
                    color?: string;
                    type?: string;
                }[];
            };
            dictFormatter: (values: DictOptions) => string;
            dictColor: boolean;
            dictSeparator: string;
            dictAllLevels: boolean;
            buttons: ((options: {
                scope: any;
            }) => ClTable.OpButton) | ("info" | "delete" | "edit" | AnyString | `slot-${string}` | {
                [x: string]: any;
                label: string;
                type?: string;
                hidden?: boolean;
                onClick: (options: {
                    scope: obj;
                }) => void;
            })[];
            align: ElementPlus.Align;
            label: any;
            renderLabel: (options: {
                column: any;
                $index: number;
            }) => any;
            className: string;
            prop: string & {};
            orderNum: number;
            width: string | number | {
                value: string | number;
            };
            minWidth: string | number | {
                value: string | number;
            };
            renderHeader: (options: {
                column: any;
                $index: number;
            }) => any;
            sortable: boolean | "desc" | "descending" | "ascending" | "asc" | "custom";
            sortMethod: fn;
            sortBy: string | any[] | ((row: any, index: number) => any);
            resizable: boolean;
            columnKey: string;
            headerAlign: ElementPlus.Align;
            showOverflowTooltip: boolean;
            fixed: boolean | string;
            render: (row: any, column: any, value: any, index: number) => any;
            formatter: (row: any, column: any, value: any, index: number) => any;
            selectable: (row: any, index: number) => boolean;
            reserveSelection: boolean;
            filterMethod: fn;
            filteredValue: unknown[];
            filters: unknown[];
            filterPlacement: string;
            filterMultiple: boolean;
            index: ((index: number) => number) | number;
            sortOrders: unknown[];
            children: /*elided*/ any[];
        }[];
        autoHeight: boolean;
        height: any;
        contextMenu: ("info" | "update" | "delete" | "edit" | "refresh" | {
            [x: string]: any;
            label: string;
            prefixIcon?: any;
            suffixIcon?: any;
            ellipsis?: boolean;
            disabled?: boolean;
            hidden?: boolean;
            children?: /*elided*/ any[];
            showChildren?: boolean;
            callback?: (done: fn) => void;
        } | ((row: obj, column: obj, event: PointerEvent) => ClContextMenu.Item) | "check" | "order-desc" | "order-asc")[];
        defaultSort: {
            prop: string;
            order: "descending" | "ascending";
        };
        sortRefresh: boolean;
        emptyText: string;
        rowKey: string;
        on?: {
            [key: string]: (...args: any[]) => void;
        };
        props?: {
            [key: string]: any;
        };
        plugins?: ClTable.Plugin[];
        onRowContextmenu?: (row: any, column: any, event: any) => void;
    };
};
export * from './data';
export * from './height';
export * from './op';
export * from './render';
export * from './row';
export * from './selection';
export * from './sort';
export * from './header';
