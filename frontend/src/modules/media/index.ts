// 媒体资源模块入口。
// useAssetUrl 是跨模块公共 API（media 与 workflow 的产物/日志视图共用），
// 外部一律 `import { useAssetUrl } from '/$/media'`，不直接引深层路径。
export { useAssetUrl } from './composables/use-asset-url';
