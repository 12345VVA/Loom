/**
 * 从 LLM/工具节点的嵌套响应中递归提取图片数据数组。
 * 从 image.vue 抽出（修复批次4），便于单元测试。
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
