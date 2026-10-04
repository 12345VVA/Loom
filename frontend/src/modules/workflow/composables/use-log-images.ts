/**
 * 工作流日志抽屉的图片提取与打包下载。
 * 自 log-drawer.vue 抽出（script 段 43%）：深层挖掘节点产物中的图片、
 * 节点内/跨节点去重、一键打包下载。
 */
import { computed, ref, type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import type { WorkflowLogItem } from '../utils';
import { downloadImagesAsZip, type ImageDownloadItem } from '../utils/download';
import { useAssetUrl } from '/$/media';
import type { TranslateFn } from '../utils/log-format';

export function useLogImages(options: { items: Ref<WorkflowLogItem[]>; t: TranslateFn }) {
	const { items, t } = options;
	const { assetUrl, ensureDownloadToken } = useAssetUrl();

	const downloadingAllZip = ref(false);
	const downloadAllProgressText = ref('');

	function resolveUrl(url: string): string {
		if (!url) return '';
		const s = url.trim();
		if (s.startsWith('data:image/') || s.startsWith('blob:')) {
			return s;
		}
		// 任何包含 /uploads/ 的路径，统一经由 assetUrl 剥离旧 token 并注入当前有效 token
		if (s.includes('/uploads/')) {
			return assetUrl(s);
		}
		if (s.startsWith('http://') || s.startsWith('https://')) {
			return s;
		}
		const normalized = s.startsWith('/') ? s : `/${s}`;
		return assetUrl(normalized);
	}

	function isLikelyImageUrl(key: string, val: string): boolean {
		if (!val || typeof val !== 'string') return false;
		const s = val.trim();

		// 1. 基础长度限制：一个有效图片路径通常至少为 5 个字符（如 a.png）
		if (s.length < 5 || s.length > 2000) return false;

		// 2. 绝对安全性检查：图片 URL 绝不能包含空格、换行、制表符或中文标点符号
		if (/[\s\n\r\t，。！？“”《》]/.test(s)) {
			return false;
		}

		// 3. 字段名黑名单：提示词、文案、标题、描述、代码等文本字段坚决排除
		const nonImgKeyRegex =
			/(prompt|text|desc|instruction|query|param|title|message|content|article|script|schema|code|token|header|note|point)/i;
		if (nonImgKeyRegex.test(key)) {
			return false;
		}

		// 4. Base64 图片 (以 data:image/ 开头)
		if (s.startsWith('data:image/')) {
			return true;
		}

		// 5. 清除 query 参数和 hash 后的干净路径
		const cleanUrl = s.split('?')[0].split('#')[0];
		const hasImgExt = /\.(png|jpe?g|webp|gif|svg|bmp|tiff|avif|ico)$/i.test(cleanUrl);

		// 6. 本地静态资源目录（/uploads/ 或 /static/，支持前导斜杠或无斜杠）
		const isLocalStaticPath =
			cleanUrl.startsWith('/uploads/') ||
			cleanUrl.startsWith('uploads/') ||
			cleanUrl.includes('/uploads/') ||
			cleanUrl.startsWith('/static/') ||
			cleanUrl.startsWith('static/') ||
			cleanUrl.includes('/static/');

		if (isLocalStaticPath) {
			// 本地上传路径必须带有合法图片扩展名，或带有明确图片属性名
			if (hasImgExt) return true;
			const explicitImgKey = /^(image|image_url|cover|cover_image_url|img|pic|photo|thumbnail)$/i;
			if (explicitImgKey.test(key) && cleanUrl.includes('/')) return true;
		}

		// 7. 远端 Web URL (http:// 或 https://)
		const isHttp = cleanUrl.startsWith('http://') || cleanUrl.startsWith('https://');
		if (isHttp) {
			if (hasImgExt) return true;
			// 动态签名无扩展名图片必须有强图片字段名
			const explicitImgKey =
				/^(image|image_url|cover|cover_image_url|img|pic|photo|thumbnail|artwork)$/i;
			if (explicitImgKey.test(key)) return true;
		}

		// 8. 相对路径（以 / 或 ./ 开头）必须具备图片扩展名
		if ((cleanUrl.startsWith('/') || cleanUrl.startsWith('./')) && hasImgExt) {
			return true;
		}

		return false;
	}

	/**
	 * 从任意载荷数据中深层挖掘图片（支持对象、循环结果数组、纯图片字符串数组、嵌套序列化子 JSON）
	 */
	function extractRawImagesFromData(data: unknown, nodeName?: string): ImageDownloadItem[] {
		if (!data) return [];
		let parsed: unknown = data;
		if (typeof data === 'string') {
			const trimmed = data.trim();
			if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
				try {
					parsed = JSON.parse(data);
				} catch {
					parsed = null;
				}
			} else {
				parsed = null;
			}
		}

		const list: ImageDownloadItem[] = [];
		const seenUrls = new Set<string>();

		function checkAndAdd(val: string, key: string, parentObj: Record<string, unknown> | null) {
			if (isLikelyImageUrl(key, val)) {
				const resolved = resolveUrl(val);
				if (resolved && !seenUrls.has(resolved)) {
					seenUrls.add(resolved);

					let subtitle = '';
					if (parentObj) {
						if (parentObj.story_text) subtitle = String(parentObj.story_text);
						else if (parentObj.scene_prompt) subtitle = String(parentObj.scene_prompt);
						else if (parentObj.prompt) subtitle = String(parentObj.prompt);
						else if (parentObj.paragraph_id) subtitle = `段落 ${parentObj.paragraph_id}`;
						else if (parentObj.page_number) subtitle = `第 ${parentObj.page_number} 页`;
						else if (parentObj.index !== undefined) subtitle = `#${Number(parentObj.index) + 1}`;
					}

					let title = key;
					if (key === 'cover_image_url' || key === 'cover') title = t('封面图');
					else if (key === 'image_url' || key === 'image' || key === 'img') title = t('插图');
					else if (parentObj && parentObj.paragraph_id) title = `${t('段落')} ${parentObj.paragraph_id}`;

					list.push({
						url: resolved,
						title: title || nodeName || 'image',
						subtitle
					});
				}
			}
		}

		function traverse(obj: unknown, currentKey = '') {
			if (!obj) return;

			// 核心：支持数组（纯图片字符串数组或对象数组）
			if (Array.isArray(obj)) {
				obj.forEach((item, idx) => {
					const itemKey = currentKey ? `${currentKey}[${idx}]` : `[${idx}]`;
					if (typeof item === 'string') {
						const trimmed = item.trim();
						// 如果数组元素也是序列化 JSON 字符串，尝试深层解析
						if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
							try {
								const sub = JSON.parse(trimmed);
								traverse(sub, itemKey);
								return;
							} catch {
								// 忽略解析失败，继续作为普通字符串匹配
							}
						}
						checkAndAdd(item, itemKey, null);
					} else if (typeof item === 'object' && item !== null) {
						traverse(item, itemKey);
					}
				});
				return;
			}

			if (typeof obj !== 'object') return;

			for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
				const fullKey = currentKey ? `${currentKey}.${k}` : k;
				if (typeof v === 'string') {
					const trimmed = v.trim();
					// 关键：循环节点或大模型输出常将子 JSON 序列化存储在字段中，深层递归解析
					if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
						try {
							const sub = JSON.parse(trimmed);
							traverse(sub, fullKey);
							continue;
						} catch {
							// 降级为常规字符串处理
						}
					}
					checkAndAdd(v, k, obj as Record<string, unknown>);
				} else if (typeof v === 'object' && v !== null) {
					traverse(v, fullKey);
				}
			}
		}

		if (parsed) {
			traverse(parsed);
		}

		// 无论之前解析如何，若未挖出图片或文本中存在漏网的 uploads 路径，进行正则扫描兜底
		const rawStr = typeof data === 'string' ? data : JSON.stringify(data);
		if (rawStr && (list.length === 0 || rawStr.includes('/uploads/') || rawStr.includes('uploads/'))) {
			const regex =
				/(?:https?:\/\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?|(?:(?:\/|\b)uploads\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?)|(?:(?:\/|\b)static\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?))/gi;
			let m;
			while ((m = regex.exec(rawStr)) !== null) {
				const u = resolveUrl(m[0]);
				if (u && !seenUrls.has(u)) {
					seenUrls.add(u);
					list.push({ url: u, title: nodeName || 'image' });
				}
			}
		}

		return list;
	}

	/**
	 * 每个节点自身所包含的有效图片列表（节点内部独立去重）
	 * 确保循环节点、结束节点（汇总整场产物）均能完整展示属于该节点的图片产物画廊
	 */
	const nodeProducedImagesMap = computed<Map<unknown, ImageDownloadItem[]>>(() => {
		const map = new Map<unknown, ImageDownloadItem[]>();

		items.value.forEach((item, index) => {
			const key = item.id !== undefined && item.id !== null ? item.id : index;

			// 开始节点作为工作流纯入口参数，不作为图片产出步骤
			if (item.nodeType === 'start') {
				map.set(key, []);
				return;
			}

			// 提取该节点产物中的图片（严格优先使用本次节点执行的 outputData）
			const payload =
				item.outputData !== undefined && item.outputData !== null && item.outputData !== ''
					? item.outputData
					: item.inputData;
			const rawImages = extractRawImagesFromData(payload, item.nodeName);

			// 该节点内部根据 URL 去重
			const nodeSeen = new Set<string>();
			const uniqueImages: ImageDownloadItem[] = [];
			rawImages.forEach(img => {
				if (!nodeSeen.has(img.url)) {
					nodeSeen.add(img.url);
					uniqueImages.push(img);
				}
			});

			map.set(key, uniqueImages);
		});

		return map;
	});

	/**
	 * 获取单个节点的图片列表
	 */
	function extractNodeImages(item: WorkflowLogItem): ImageDownloadItem[] {
		if (!item) return [];
		const index = items.value.indexOf(item);
		const key = item.id !== undefined && item.id !== null ? item.id : index;
		return nodeProducedImagesMap.value.get(key) || [];
	}

	/** 辅助检测：是否含有图片产物（基于精确提取与节点类型过滤） */
	function hasDetectedImages(item: WorkflowLogItem): boolean {
		return extractNodeImages(item).length > 0;
	}

	function getImageCount(item: WorkflowLogItem): number {
		return extractNodeImages(item).length;
	}

	/**
	 * 收集提取整场工作流所有节点的真实图片产物（全局跨节点 URL 去重汇总）
	 * 用于顶部全景指标看板显示总数以及顶部工具栏“一键全量打包下载”
	 */
	const allWorkflowImages = computed<ImageDownloadItem[]>(() => {
		const list: ImageDownloadItem[] = [];
		const seenUrls = new Set<string>();

		items.value.forEach(item => {
			const imgs = extractNodeImages(item);
			imgs.forEach(img => {
				if (!seenUrls.has(img.url)) {
					seenUrls.add(img.url);
					list.push(img);
				}
			});
		});

		// 兜底：若节点提取为空，从全文原始字符串扫描
		if (list.length === 0) {
			items.value.forEach(item => {
				const str = (item.outputData || '') + (item.inputData || '');
				const imgs = extractRawImagesFromData(str, item.nodeName);
				imgs.forEach(img => {
					if (!seenUrls.has(img.url)) {
						seenUrls.add(img.url);
						list.push(img);
					}
				});
			});
		}

		return list;
	});

	async function handleDownloadAllImages() {
		if (allWorkflowImages.value.length === 0) {
			ElMessage.warning(t('暂无生成图片产物'));
			return;
		}

		downloadingAllZip.value = true;
		downloadAllProgressText.value = `0/${allWorkflowImages.value.length}`;

		try {
			// 确保下载令牌最新有效，杜绝长时间停留导致的 401
			await ensureDownloadToken(true);

			const itemsToDownload = allWorkflowImages.value.map(img => {
				const finalUrl = assetUrl(img.url) || img.url;
				return {
					url: finalUrl,
					title: img.title,
					subtitle: img.subtitle
				};
			});

			const instId = items.value[0]?.instanceId || 'all';
			const zipName = `workflow_inst${instId}_images_${Date.now()}.zip`;
			await downloadImagesAsZip(itemsToDownload, zipName, (curr, total) => {
				downloadAllProgressText.value = `${curr}/${total}`;
			});
		} catch (e) {
			const message = e instanceof Error ? e.message : String(e);
			ElMessage.error(t('打包下载失败: ') + message);
		} finally {
			downloadingAllZip.value = false;
			downloadAllProgressText.value = '';
		}
	}

	return {
		downloadingAllZip,
		downloadAllProgressText,
		extractRawImagesFromData,
		nodeProducedImagesMap,
		extractNodeImages,
		hasDetectedImages,
		getImageCount,
		allWorkflowImages,
		handleDownloadAllImages
	};
}
