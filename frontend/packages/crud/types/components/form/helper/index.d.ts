export declare function useForm(): {
    Form: import('vue').Ref<any, any>;
    config: {
        [x: string]: any;
        title?: any;
        height?: any;
        width?: any;
        props: {
            [x: string]: any;
            inline?: boolean;
            labelPosition?: "left" | "right" | "top";
            labelWidth?: string | number;
            labelSuffix?: string;
            hideRequiredAsterisk?: boolean;
            showMessage?: boolean;
            inlineMessage?: boolean;
            statusIcon?: boolean;
            validateOnRuleChange?: boolean;
            size?: ElementPlus.Size;
            disabled?: boolean;
        };
        items: {
            [x: string]: any;
            type?: "tabs";
            prop?: string & {};
            props?: {
                [x: string]: any;
                labels?: {
                    [x: string]: any;
                    label: string;
                    value: string;
                    name?: string;
                    icon?: any;
                    lazy?: boolean;
                }[];
                justify?: "left" | "center" | "right";
                color?: string;
                mergeProp?: boolean;
                labelWidth?: string;
                error?: string;
                showMessage?: boolean;
                inlineMessage?: boolean;
                size?: "medium" | "default" | "small";
            };
            span?: number;
            col?: {
                span: number;
                offset: number;
                push: number;
                pull: number;
                xs: any;
                sm: any;
                md: any;
                lg: any;
                xl: any;
                tag: string;
            };
            group?: string;
            collapse?: boolean;
            value?: any;
            label?: string;
            renderLabel?: any;
            flex?: boolean;
            hook?: "string" | "number" | "boolean" | "join" | "split" | AnyString | "empty" | "booleanNumber" | "datetimeRange" | "splitJoin" | "json" | {
                bind?: ClForm.Hook["Pipe"] | ClForm.Hook["Pipe"][];
                submit?: ClForm.Hook["Pipe"] | ClForm.Hook["Pipe"][];
                reset?: (prop: string) => string[];
            };
            hidden?: boolean | ((options: {
                scope: obj;
            }) => boolean);
            prepend?: {
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
            component?: {
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
            append?: {
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
            rules?: {
                [x: string]: any;
                type?: "string" | "number" | "boolean" | "method" | "regexp" | "integer" | "float" | "array" | "object" | "enum" | "date" | "url" | "hex" | "email" | "any";
                required?: boolean;
                message?: string;
                min?: number;
                max?: number;
                trigger?: any;
                validator?: (rule: any, value: any, callback: (error?: Error) => void) => void;
            } | {
                [x: string]: any;
                type?: "string" | "number" | "boolean" | "method" | "regexp" | "integer" | "float" | "array" | "object" | "enum" | "date" | "url" | "hex" | "email" | "any";
                required?: boolean;
                message?: string;
                min?: number;
                max?: number;
                trigger?: any;
                validator?: (rule: any, value: any, callback: (error?: Error) => void) => void;
            }[];
            required?: boolean;
            children?: /*elided*/ any[];
        }[];
        form: obj;
        isReset?: boolean;
        on?: {
            open?: (data: any) => void;
            close?: (action: ClForm.CloseAction, done: fn) => void;
            submit?: (data: any, event: {
                close: fn;
                done: fn;
            }) => void;
            change?: (data: any, prop: string) => void;
        };
        op: {
            hidden?: boolean;
            saveButtonText?: string;
            closeButtonText?: string;
            justify?: "flex-start" | "center" | "flex-end";
            buttons?: (`slot-${string}` | ClForm.CloseAction | {
                [x: string]: any;
                label: string;
                type?: string;
                hidden?: boolean;
                onClick: (options: {
                    scope: obj;
                }) => void;
            })[];
        };
        dialog: {
            [x: string]: any;
            title?: any;
            height?: string;
            width?: string;
            hideHeader?: boolean;
            controls?: Array<"fullscreen" | "close" | AnyString>;
        };
    };
    form: obj;
    visible: import('vue').Ref<boolean, boolean>;
    saving: import('vue').Ref<boolean, boolean>;
    loading: import('vue').Ref<boolean, boolean>;
    disabled: import('vue').Ref<boolean, boolean>;
};
export * from './action';
export * from './api';
export * from './plugins';
export * from './tabs';
