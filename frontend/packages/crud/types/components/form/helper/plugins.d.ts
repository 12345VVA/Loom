import { Ref } from 'vue';
export declare function usePlugins(enable: boolean, { visible }: {
    visible: Ref<boolean>;
}): {
    create: (plugins?: ClForm.Plugin[]) => boolean;
    submit: (data: any) => Promise<any>;
};
