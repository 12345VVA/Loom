import { Ref } from 'vue';
export declare function useCrud(options?: ClCrud.Options, cb?: (app: ClCrud.Ref) => void): Ref<ClCrud.Ref, ClCrud.Ref>;
export declare function useUpsert<T = any>(options?: ClUpsert.Options<T>): Ref<ClUpsert.Ref<any>, ClUpsert.Ref<any>>;
export declare function useTable<T = any>(options?: ClTable.Options<T>, cb?: (table: ClTable.Ref) => void): Ref<ClTable.Ref<T>, ClTable.Ref<T>>;
export declare function useForm<T = any>(cb?: (app: ClForm.Ref<T>) => void): Ref<ClForm.Ref<T>, ClForm.Ref<T>>;
export declare function useAdvSearch<T = any>(options?: ClAdvSearch.Options<T>): Ref<ClAdvSearch.Ref<T>, ClAdvSearch.Ref<T>>;
export declare function useSearch<T = any>(options?: ClSearch.Options<T>): Ref<ClSearch.Ref<T>, ClSearch.Ref<T>>;
export declare function useDialog(options?: {
    onFullscreen(visible: boolean): void;
}): ClDialog.Provide;
