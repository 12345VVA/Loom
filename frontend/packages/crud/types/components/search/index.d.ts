import { PropType } from 'vue';
declare const _default: import('vue').DefineComponent<import('vue').ExtractPropTypes<{
    inline: {
        type: BooleanConstructor;
        default: boolean;
    };
    props: {
        type: ObjectConstructor;
        default: () => {};
    };
    data: {
        type: ObjectConstructor;
        default: () => {};
    };
    items: {
        type: PropType<ClForm.Item[]>;
        default: () => any[];
    };
    resetBtn: {
        type: BooleanConstructor;
        default: boolean;
    };
    collapse: {
        type: BooleanConstructor;
        default: boolean;
    };
    onLoad: FunctionConstructor;
    onSearch: FunctionConstructor;
}>, () => any, {}, {}, {}, import('vue').ComponentOptionsMixin, import('vue').ComponentOptionsMixin, "reset"[], "reset", import('vue').PublicProps, Readonly<import('vue').ExtractPropTypes<{
    inline: {
        type: BooleanConstructor;
        default: boolean;
    };
    props: {
        type: ObjectConstructor;
        default: () => {};
    };
    data: {
        type: ObjectConstructor;
        default: () => {};
    };
    items: {
        type: PropType<ClForm.Item[]>;
        default: () => any[];
    };
    resetBtn: {
        type: BooleanConstructor;
        default: boolean;
    };
    collapse: {
        type: BooleanConstructor;
        default: boolean;
    };
    onLoad: FunctionConstructor;
    onSearch: FunctionConstructor;
}>> & Readonly<{
    onReset?: (...args: any[]) => any;
}>, {
    data: Record<string, any>;
    props: Record<string, any>;
    items: ClForm.Item<any>[];
    inline: boolean;
    resetBtn: boolean;
    collapse: boolean;
}, {}, {}, {}, string, import('vue').ComponentProvideOptions, true, {}, any>;
export default _default;
