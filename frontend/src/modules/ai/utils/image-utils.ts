/**
 * 从 LLM/工具节点的嵌套响应中递归提取图片数据。
 * 自 views/image-utils.ts 迁入（views/ 会被路由 glob 误扫），并统一
 * image.vue / profile.vue / task.vue 三处重复实现（profile/task 为无深度保护的旧拷贝）。
 *
 * 深度限制：异常嵌套数据（超深结构 / 循环引用）不再导致栈溢出。
 */
const MAX_DEPTH = 5;

export function findImageData(value: any, depth = MAX_DEPTH): any[] {
	if (depth <= 0 || !value) {
		return [];
	}
	if (typeof value === 'string') {
		try {
			return findImageData(JSON.parse(value), depth - 1);
		} catch {
			return [];
		}
	}
	if (Array.isArray(value)) {
		return value;
	}
	if (Array.isArray(value.data)) {
		return value.data;
	}
	if (value.resultPayload) {
		return findImageData(value.resultPayload, depth - 1);
	}
	if (value.raw) {
		const rawItems = findImageData(value.raw, depth - 1);
		if (rawItems.length) {
			return rawItems;
		}
	}
	if (value.output) {
		const outputItems = findImageData(value.output, depth - 1);
		if (outputItems.length) {
			return outputItems;
		}
	}
	if (value.result) {
		return findImageData(value.result, depth - 1);
	}
	if (Array.isArray(value.images)) {
		return value.images;
	}
	return [];
}

export interface ImageItem {
	src: string;
	value: string;
	url?: string;
}

/**
 * 将 findImageData 的结果规整为可预览的图片项（url 或 base64 data URI）。
 */
export function extractImageItems(value: any): ImageItem[] {
	const items = findImageData(value);
	return items
		.map(item => {
			const url = item?.url || item?.image_url || item?.imageUrl || item?.image;
			const b64 = item?.b64_json || item?.b64Json || item?.base64;
			if (url) {
				return { src: url, value: url, url };
			}
			if (b64) {
				const src = String(b64).startsWith('data:image')
					? String(b64)
					: `data:image/png;base64,${b64}`;
				return { src, value: String(b64) };
			}
			return null;
		})
		.filter(Boolean) as ImageItem[];
}
