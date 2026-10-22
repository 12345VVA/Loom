// IP 资产库模块对外 API 出口（module.mdc：跨模块引用一律走 /$/asset）。
export { default as ComposerPreview } from './components/composer-preview.vue';
export type { ComposerPreviewPayload } from './components/composer-preview.vue';

export function useAsset() {
	return {};
}
