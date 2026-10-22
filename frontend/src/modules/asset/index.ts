// IP 资产库模块对外 API 出口（module.mdc：跨模块引用一律走 /$/asset）。
// 三库页面的共享逻辑在 ./composables/use-asset-library（模块内使用，不对外导出）。
export { default as ComposerPreview } from './components/composer-preview.vue';
export type { ComposerPreviewPayload } from './components/composer-preview.vue';
