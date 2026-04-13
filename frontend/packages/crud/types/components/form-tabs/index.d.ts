import { PropType } from 'vue';
declare const _default: import('vue').DefineComponent<import('vue').ExtractPropTypes<{
    modelValue: (NumberConstructor | StringConstructor)[];
    labels: {
        type: ArrayConstructor;
        default: () => any[];
    };
    justify: {
        type: PropType<"start" | "end" | "left" | "right" | "center" | "justify" | "match-parent">;
        default: string;
    };
    type: {
        type: PropType<"card" | "default">;
        default: string;
    };
}>, () => any, {}, {}, {}, import('vue').ComponentOptionsMixin, import('vue').ComponentOptionsMixin, ("change" | "update:modelValue")[], "change" | "update:modelValue", import('vue').PublicProps, Readonly<import('vue').ExtractPropTypes<{
    modelValue: (NumberConstructor | StringConstructor)[];
    labels: {
        type: ArrayConstructor;
        default: () => any[];
    };
    justify: {
        type: PropType<"start" | "end" | "left" | "right" | "center" | "justify" | "match-parent">;
        default: string;
    };
    type: {
        type: PropType<"card" | "default">;
        default: string;
    };
}>> & Readonly<{
    onChange?: (...args: any[]) => any;
    "onUpdate:modelValue"?: (...args: any[]) => any;
}>, {
    type: "default" | "card";
    labels: unknown[];
    justify: "left" | "center" | "right" | "justify" | "start" | "end" | "match-parent";
}, {}, {}, {}, string, import('vue').ComponentProvideOptions, true, {}, any>;
export default _default;
