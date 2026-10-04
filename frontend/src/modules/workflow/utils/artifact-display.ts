/**
 * 工作流产物 → 展示项派生（纯函数，从 artifact-drawer.vue 拆出）。
 *
 * 职责：把 artifact.page 返回的原始产物列表整理成抽屉可直接渲染的
 * DisplayItem 列表——图片产物解析访问地址、文本/JSON 产物探测内嵌图片
 * （如内页图片循环输出数组）、按原始 URL 全程去重。
 */

export interface ArtifactItem {
	id: number;
	instanceId?: number;
	definitionId?: number;
	versionId?: number;
	nodeId?: string | null;
	fieldKey: string;
	fieldPath?: string | null;
	assetType: string;
	mediaAssetId?: number | null;
	storageUrl?: string | null;
	originalUrl?: string | null;
	content?: string | null;
	contentRef?: string | null;
}

export interface DisplayItem {
	id: number;
	fieldKey: string;
	fieldPath?: string;
	assetType: string;
	src: string;
	copyText: string;
	display: string;
}

/** 启发式判断字符串是否像图片 URL（用于从 JSON 产物里探测内嵌图片）。 */
export function isLikelyImageUrl(str: string): boolean {
	if (!str || typeof str !== 'string') return false;
	const s = str.trim();
	if (s.includes(' ') || s.includes('\n')) return false;
	if (s.includes('uploads/')) return true;
	if (/^https?:\/\//i.test(s)) {
		const clean = s.split('?')[0].toLowerCase();
		if (/\.(png|jpe?g|webp|gif|svg|bmp|avif)$/i.test(clean)) return true;
		if (s.includes('.tos-') || s.includes('.oss-') || s.includes('.myqcloud.com') || s.includes('/doubao-')) return true;
	}
	return false;
}

/** 深度遍历 JSON 数据，收集疑似图片 URL 及其字段路径。 */
export function findImagesInData(data: unknown, prefix = ''): Array<{ url: string; path: string }> {
	const list: Array<{ url: string; path: string }> = [];
	if (!data) return list;

	function walk(val: unknown, currentPath: string) {
		if (typeof val === 'string' && isLikelyImageUrl(val)) {
			list.push({ url: val, path: currentPath });
		} else if (Array.isArray(val)) {
			val.forEach((item, i) => {
				walk(item, `${currentPath}.${i}`);
			});
		} else if (typeof val === 'object' && val !== null) {
			for (const [k, v] of Object.entries(val)) {
				if (k === 'error' || k === 'prompt' || k === 'desc' || k === 'text' || k === 'scene_prompt') continue;
				// 内部通道变量（__src 厂商临时 URL，约 24h 过期）：供下游节点引用，不作为图片渲染
				if (k.endsWith('__src')) continue;
				walk(v, `${currentPath}.${k}`);
			}
		}
	}

	walk(data, prefix);
	return list;
}

/**
 * 产物列表 → 展示项列表。
 *
 * 图片按原始 URL 全程去重：后端图片产物与 json 产物（内嵌图片探测）并存、
 * 以及循环快照重复携带外层图片时，同一 URL 只展示/打包一张。
 *
 * @param items 原始产物列表
 * @param assetUrl 原始地址 → 访问地址转换（media 模块 useAssetUrl 的 assetUrl）
 * @param formatJson 文本/JSON 美化函数
 */
export function buildDisplayItems(
	items: ArtifactItem[],
	assetUrl: (raw: string) => string,
	formatJson: (raw: string) => string
): DisplayItem[] {
	const result: DisplayItem[] = [];
	const seenImageUrls = new Set<string>();

	items.forEach(item => {
		// 1. 本身即为 image 类型的产物
		if (item.assetType === 'image') {
			const raw = item.storageUrl || item.originalUrl || item.content || '';
			if (raw) {
				if (!seenImageUrls.has(raw)) {
					seenImageUrls.add(raw);
					result.push({
						id: item.id,
						fieldKey: item.fieldKey,
						fieldPath: item.fieldPath || undefined,
						assetType: 'image',
						src: assetUrl(raw),
						copyText: raw,
						display: raw
					});
				}
			}
			return;
		}

		// 2. 文本/JSON 产物：探测是否包含嵌套图片（如内页图片循环输出数组）
		const raw = item.content || item.contentRef || item.originalUrl || '';
		let extractedImages: Array<{ url: string; path: string }> = [];

		if (raw && (raw.startsWith('[') || raw.startsWith('{'))) {
			try {
				const parsed: unknown = JSON.parse(raw);
				extractedImages = findImagesInData(parsed, item.fieldKey);
			} catch {
				// not json
			}
		}

		// 如果成功提取到了图片（例如 inner_images 数组）
		if (extractedImages.length > 0) {
			extractedImages.forEach((img, idx) => {
				if (seenImageUrls.has(img.url)) return;
				seenImageUrls.add(img.url);
				result.push({
					id: Number(`${item.id}00${idx}`),
					fieldKey: item.fieldKey,
					fieldPath: img.path,
					assetType: 'image',
					src: assetUrl(img.url),
					copyText: img.url,
					display: img.url
				});
			});
		}

		// 依然保留原文本/JSON 结构卡片展示
		result.push({
			id: item.id,
			fieldKey: item.fieldKey,
			fieldPath: item.fieldPath || undefined,
			assetType: item.assetType,
			src: '',
			copyText: raw,
			display: formatJson(raw)
		});
	});

	return result;
}
