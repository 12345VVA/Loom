export declare function useHeight({ config, Table }: {
    Table: Vue.Ref<any>;
    config: ClTable.Config;
}): {
    maxHeight: import('vue').Ref<number, number>;
    calcMaxHeight: import('lodash').DebouncedFunc<() => Promise<void>>;
};
