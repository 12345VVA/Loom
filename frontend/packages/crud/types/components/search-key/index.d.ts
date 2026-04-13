import { PropType } from 'vue';
declare const _default: import('vue').DefineComponent<import('vue').ExtractPropTypes<{
    modelValue: StringConstructor;
    field: {
        type: StringConstructor;
        default: string;
    };
    fieldList: {
        type: PropType<Array<{
            label: string;
            value: string;
        }>>;
        default: () => any[];
    };
    onSearch: FunctionConstructor;
    placeholder: StringConstructor;
    width: {
        type: (NumberConstructor | StringConstructor)[];
        default: number;
    };
    refreshOnInput: BooleanConstructor;
}>, () => any, {}, {}, {}, import('vue').ComponentOptionsMixin, import('vue').ComponentOptionsMixin, ("change" | "update:modelValue" | "field-change")[], "change" | "update:modelValue" | "field-change", import('vue').PublicProps, Readonly<import('vue').ExtractPropTypes<{
    modelValue: StringConstructor;
    field: {
        type: StringConstructor;
        default: string;
    };
    fieldList: {
        type: PropType<Array<{
            label: string;
            value: string;
        }>>;
        default: () => any[];
    };
    onSearch: FunctionConstructor;
    placeholder: StringConstructor;
    width: {
        type: (NumberConstructor | StringConstructor)[];
        default: number;
    };
    refreshOnInput: BooleanConstructor;
}>> & Readonly<{
    onChange?: (...args: any[]) => any;
    "onUpdate:modelValue"?: (...args: any[]) => any;
    "onField-change"?: (...args: any[]) => any;
}>, {
    width: string | number;
    refreshOnInput: boolean;
    field: string;
    fieldList: {
        label: string;
        value: string;
    }[];
}, {}, {}, {}, string, import('vue').ComponentProvideOptions, true, {}, any>;
export default _default;
