export declare const format: {
    [key: string]: ClForm.Hook["Fn"];
};
declare const formHook: {
    bind(data: any): void;
    submit(data: any): void;
};
export declare function registerFormHook(name: string, fn: ClForm.Hook["Fn"]): void;
export default formHook;
