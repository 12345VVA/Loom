import { App } from 'vue';
declare const Crud: {
    install(app: App, options?: any): {
        name: string;
    };
};
export { Crud };
export * from './emitter';
export * from './hooks';
export * from './locale';
export { registerFormHook } from './utils/form-hook';
export { renderNode } from './utils/vnode';
export { ContextMenu } from './components/context-menu';
