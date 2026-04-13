import { PropType } from 'vue';
declare const _default: import('vue').DefineComponent<import('vue').ExtractPropTypes<{
    items: {
        type: PropType<ClForm.Item[]>;
        default: () => any[];
    };
    title: StringConstructor;
    size: {
        type: (NumberConstructor | StringConstructor)[];
        default: string;
    };
    op: {
        type: ArrayConstructor;
        default: () => string[];
    };
    onSearch: FunctionConstructor;
}>, () => any, {}, {}, {}, import('vue').ComponentOptionsMixin, import('vue').ComponentOptionsMixin, ("clear" | "reset")[], "clear" | "reset", import('vue').PublicProps, Readonly<import('vue').ExtractPropTypes<{
    items: {
        type: PropType<ClForm.Item[]>;
        default: () => any[];
    };
    title: StringConstructor;
    size: {
        type: (NumberConstructor | StringConstructor)[];
        default: string;
    };
    op: {
        type: ArrayConstructor;
        default: () => string[];
    };
    onSearch: FunctionConstructor;
}>> & Readonly<{
    onReset?: (...args: any[]) => any;
    onClear?: (...args: any[]) => any;
}>, {
    size: string | number;
    items: ClForm.Item<any>[];
    op: unknown[];
}, {}, {
    Close: import('vue').DefineComponent<{}, {}, {}, {}, {}, import('vue').ComponentOptionsMixin, import('vue').ComponentOptionsMixin, {}, string, import('vue').VNodeProps & import('vue').AllowedComponentProps & import('vue').ComponentCustomProps, Readonly<import('vue').ExtractPropTypes<{}>>, {}, {}, {}, {}, string, import('vue').ComponentProvideOptions, true, {}, any>;
}, {}, string, import('vue').ComponentProvideOptions, true, {}, any>;
export default _default;
