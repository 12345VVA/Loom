// 媒体资源模块入口。
// useAssetUrl / MediaImageSelect 是跨模块公共 API（media 与 workflow/asset 视图共用），
// 外部一律 `import { useAssetUrl, MediaImageSelect } from '/$/media'`，不直接引深层路径。
export { useAssetUrl } from './composables/use-asset-url';
export { default as MediaImageSelect } from './components/media-image-select.vue';
export type { MediaImageItem } from './components/media-image-select.vue';
