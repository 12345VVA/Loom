declare const _default: import('vue').DefineComponent<import('vue').ExtractPropTypes<{
    columns: {
        type: ArrayConstructor;
        default: () => any[];
    };
    autoHeight: {
        type: BooleanConstructor;
        default: any;
    };
    height: any;
    contextMenu: {
        type: (ArrayConstructor | BooleanConstructor)[];
        default: any;
    };
    defaultSort: ObjectConstructor;
    sortRefresh: {
        type: BooleanConstructor;
        default: boolean;
    };
    emptyText: StringConstructor;
    rowKey: {
        type: StringConstructor;
        default: string;
    };
}>, () => import('vue').VNode<import('vue').RendererNode, import('vue').RendererElement, {
    [key: string]: any;
}>, {}, {}, {}, import('vue').ComponentOptionsMixin, import('vue').ComponentOptionsMixin, ("selection-change" | "sort-change")[], "selection-change" | "sort-change", import('vue').PublicProps, Readonly<import('vue').ExtractPropTypes<{
    columns: {
        type: ArrayConstructor;
        default: () => any[];
    };
    autoHeight: {
        type: BooleanConstructor;
        default: any;
    };
    height: any;
    contextMenu: {
        type: (ArrayConstructor | BooleanConstructor)[];
        default: any;
    };
    defaultSort: ObjectConstructor;
    sortRefresh: {
        type: BooleanConstructor;
        default: boolean;
    };
    emptyText: StringConstructor;
    rowKey: {
        type: StringConstructor;
        default: string;
    };
}>> & Readonly<{
    "onSelection-change"?: (...args: any[]) => any;
    "onSort-change"?: (...args: any[]) => any;
}>, {
    columns: unknown[];
    autoHeight: boolean;
    height: any;
    contextMenu: boolean | unknown[];
    sortRefresh: boolean;
    rowKey: string;
}, {}, {}, {}, string, import('vue').ComponentProvideOptions, true, {}, any>;
export default _default;
