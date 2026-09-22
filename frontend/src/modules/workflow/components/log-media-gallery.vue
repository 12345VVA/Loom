<template>
	<div class="log-media-gallery">
		<!-- 画廊顶部工具栏 -->
		<div v-if="images.length > 0" class="gallery-toolbar">
			<div class="toolbar-left">
				<el-tag size="small" type="success" effect="plain" class="count-tag">
					{{ $t('共生成') }} {{ images.length }} {{ $t('张图片') }}
				</el-tag>
			</div>
			<div class="toolbar-right">
				<el-button
					size="small"
					type="primary"
					:loading="downloadingZip"
					@click="downloadAllAsZip"
				>
					<template #icon>
						<workflow-icon name="download" :size="14" />
					</template>
					{{ downloadingZip ? downloadProgressText : $t('打包下载全部 (ZIP)') }}
				</el-button>
				<el-button size="small" text @click="copyAllUrls">
					<template #icon>
						<workflow-icon name="copy" :size="14" />
					</template>
					{{ $t('复制所有链接') }}
				</el-button>
			</div>
		</div>

		<!-- 画廊卡片网格 -->
		<div v-if="images.length > 0" class="gallery-grid">
			<div v-for="(img, idx) in images" :key="idx" class="gallery-item">
				<div class="image-wrapper">
					<el-image
						class="media-image"
						:src="resolveUrl(img.url)"
						fit="cover"
						:preview-src-list="previewList"
						:initial-index="idx"
						preview-teleported
						loading="lazy"
					>
						<template #placeholder>
							<div class="image-slot">
								<workflow-icon name="loading" :size="22" class="is-loading" />
							</div>
						</template>
						<template #error>
							<div class="image-slot error">
								<workflow-icon name="images" :size="24" />
								<span>{{ $t('加载失败') }}</span>
							</div>
						</template>
					</el-image>

					<!-- 悬浮快捷操作蒙层 -->
					<div class="image-overlay">
						<el-tooltip :content="$t('下载原图')" placement="top">
							<el-button
								circle
								size="small"
								type="primary"
								@click.stop="downloadSingle(img, idx)"
							>
								<workflow-icon name="download" :size="13" />
							</el-button>
						</el-tooltip>
						<el-tooltip :content="$t('在新窗口打开')" placement="top">
							<el-button
								circle
								size="small"
								@click.stop="openInNewTab(resolveUrl(img.url))"
							>
								<workflow-icon name="external" :size="13" />
							</el-button>
						</el-tooltip>
						<el-tooltip :content="$t('复制图片地址')" placement="top">
							<el-button
								circle
								size="small"
								@click.stop="copyUrl(resolveUrl(img.url))"
							>
								<workflow-icon name="copy" :size="13" />
							</el-button>
						</el-tooltip>
					</div>
				</div>

				<!-- 底部卡片元数据 -->
				<div class="media-meta">
					<div class="media-title" :title="img.title || img.key">
						<div class="title-left">
							<el-tag size="small" type="success" effect="plain" class="badge">
								{{ img.title || $t('产物图片') }}
							</el-tag>
							<span class="index-tag">#{{ idx + 1 }}</span>
						</div>
						<el-tooltip :content="$t('下载此图片')" placement="top">
							<el-button
								link
								type="primary"
								size="small"
								@click="downloadSingle(img, idx)"
							>
								<workflow-icon name="download" :size="14" />
							</el-button>
						</el-tooltip>
					</div>
					<div v-if="img.subtitle" class="media-subtitle" :title="img.subtitle">
						{{ img.subtitle }}
					</div>
				</div>
			</div>
		</div>
		<el-empty v-else :description="$t('暂无生成图片产物')" :image-size="80" />
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import WorkflowIcon from './workflow-icon.vue';
import { copyToClipboard } from '../utils';
import { downloadSingleImage, downloadImagesAsZip } from '../utils/download';
import { useAssetUrl } from '/$/media/composables/use-asset-url';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';

defineOptions({ name: 'workflow-log-media-gallery' });

export interface DetectedImage {
	url: string;
	key?: string;
	title?: string;
	subtitle?: string;
}

const props = defineProps<{
	data?: any;
	stepName?: string;
	list?: DetectedImage[];
}>();

const { t } = useI18n();
const { assetUrl, ensureDownloadToken } = useAssetUrl();

const downloadingZip = ref(false);
const downloadProgressText = ref('');

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

// 智能从输入或输出数据中探测图片（支持直接传入列表，或从深层数据探测）
const images = computed<DetectedImage[]>(() => {
	if (props.list && props.list.length > 0) {
		return props.list.map(i => ({
			url: i.url,
			key: i.key,
			title: i.title,
			subtitle: i.subtitle
		}));
	}
	if (!props.data) return [];
	let parsed = props.data;
	if (typeof props.data === 'string') {
		const trimmed = props.data.trim();
		if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
			try {
				parsed = JSON.parse(props.data);
			} catch {
				parsed = null;
			}
		} else {
			parsed = null;
		}
	}

	const list: DetectedImage[] = [];
	const seenUrls = new Set<string>();

	function checkAndAdd(val: string, key: string, parentObj: any) {
		if (isLikelyImageUrl(key, val)) {
			const resolved = resolveUrl(val);
			if (resolved && !seenUrls.has(resolved)) {
				seenUrls.add(resolved);

				let subtitle = '';
				if (parentObj) {
					if (parentObj.story_text) subtitle = parentObj.story_text;
					else if (parentObj.scene_prompt) subtitle = parentObj.scene_prompt;
					else if (parentObj.prompt) subtitle = parentObj.prompt;
					else if (parentObj.paragraph_id) subtitle = `段落 ${parentObj.paragraph_id}`;
					else if (parentObj.page_number) subtitle = `第 ${parentObj.page_number} 页`;
					else if (parentObj.index !== undefined)
						subtitle = `#${Number(parentObj.index) + 1}`;
				}

				let title = key;
				if (key === 'cover_image_url' || key === 'cover') title = t('封面图');
				else if (key === 'image_url' || key === 'image' || key === 'img') title = t('插图');
				else if (parentObj && parentObj.paragraph_id)
					title = `${t('段落')} ${parentObj.paragraph_id}`;

				list.push({
					url: val,
					key,
					title,
					subtitle
				});
			}
		}
	}

	function traverse(obj: any, currentKey = '') {
		if (!obj) return;

		// 核心：支持循环与批处理产生的纯字符串数组及对象数组
		if (Array.isArray(obj)) {
			obj.forEach((item, idx) => {
				const itemKey = currentKey ? `${currentKey}[${idx}]` : `[${idx}]`;
				if (typeof item === 'string') {
					const trimmed = item.trim();
					if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
						try {
							const sub = JSON.parse(trimmed);
							traverse(sub, itemKey);
							return;
						} catch {
							// 降级常规处理
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

		for (const [k, v] of Object.entries(obj)) {
			const fullKey = currentKey ? `${currentKey}.${k}` : k;
			if (typeof v === 'string') {
				const trimmed = v.trim();
				if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
					try {
						const sub = JSON.parse(trimmed);
						traverse(sub, fullKey);
						continue;
					} catch {
						// 降级常规处理
					}
				}
				checkAndAdd(v, k, obj);
			} else if (typeof v === 'object' && v !== null) {
				traverse(v, fullKey);
			}
		}
	}

	if (parsed) {
		traverse(parsed);
	}

	// 降级兜底扫描（如果未提取出图片或文本中存在漏网的 uploads 路径）
	const rawStr = typeof props.data === 'string' ? props.data : JSON.stringify(props.data);
	if (
		rawStr &&
		(list.length === 0 || rawStr.includes('/uploads/') || rawStr.includes('uploads/'))
	) {
		const regex =
			/(?:https?:\/\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?|(?:(?:\/|\b)uploads\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?)|(?:(?:\/|\b)static\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?))/gi;
		let m;
		while ((m = regex.exec(rawStr)) !== null) {
			const u = resolveUrl(m[0]);
			if (u && !seenUrls.has(u)) {
				seenUrls.add(u);
				list.push({ url: m[0], title: props.stepName || 'image' });
			}
		}
	}

	return list;
});

const previewList = computed(() => images.value.map(i => resolveUrl(i.url)));

function copyUrl(url: string) {
	copyToClipboard(url, t('复制成功'), t('复制失败'));
}

function openInNewTab(url: string) {
	window.open(url, '_blank');
}

async function downloadSingle(img: DetectedImage, idx: number) {
	await ensureDownloadToken(true);
	const resolved = assetUrl(img.url) || resolveUrl(img.url);

	const cleanUrl = resolved.split('?')[0];
	const extMatch = cleanUrl.match(/\.(png|jpe?g|webp|gif|svg)$/i);
	const ext = extMatch ? extMatch[0].toLowerCase() : '.jpeg';

	let name = `${String(idx + 1).padStart(2, '0')}_${img.title || 'image'}`;
	if (img.subtitle) {
		const safeSub = img.subtitle
			.replace(/[\\/:*?"<>|\r\n]/g, '')
			.trim()
			.substring(0, 20);
		name = `${String(idx + 1).padStart(2, '0')}_${safeSub}`;
	}
	downloadSingleImage(resolved, `${name}${ext}`);
}

async function downloadAllAsZip() {
	if (images.value.length === 0) return;
	downloadingZip.value = true;
	downloadProgressText.value = `0/${images.value.length}`;

	try {
		// 确保下载令牌最新有效，杜绝长时间停留导致的 401
		await ensureDownloadToken(true);

		const itemsToDownload = images.value.map(img => {
			const finalUrl = assetUrl(img.url) || resolveUrl(img.url);
			return {
				url: finalUrl,
				title: img.title,
				subtitle: img.subtitle
			};
		});

		const zipName = `${props.stepName || 'workflow'}_images_${Date.now()}.zip`;
		await downloadImagesAsZip(itemsToDownload, zipName, (curr, total) => {
			downloadProgressText.value = `${curr}/${total}`;
		});
	} catch (e: any) {
		ElMessage.error(t('打包下载失败: ') + (e.message || e));
	} finally {
		downloadingZip.value = false;
		downloadProgressText.value = '';
	}
}

function copyAllUrls() {
	const text = images.value.map(i => resolveUrl(i.url)).join('\n');
	copyToClipboard(text, t('复制所有链接成功'), t('复制失败'));
}
</script>

<style lang="scss" scoped>
.log-media-gallery {
	padding: 4px 0;

	.gallery-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 12px;
		padding: 8px 12px;
		background: var(--el-fill-color-light);
		border-radius: 8px;
		border: 1px solid var(--el-border-color-lighter);

		.toolbar-left {
			display: flex;
			align-items: center;
			gap: 8px;

			.count-tag {
				font-weight: 500;
			}
		}

		.toolbar-right {
			display: flex;
			align-items: center;
			gap: 6px;
		}
	}

	.gallery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
		gap: 12px;
	}

	.gallery-item {
		border: 1px solid var(--el-border-color-lighter);
		border-radius: 8px;
		background: var(--el-bg-color-overlay);
		overflow: hidden;
		transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);

		&:hover {
			border-color: var(--el-color-primary-light-5);
			box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
			transform: translateY(-2px);

			.image-overlay {
				opacity: 1;
			}
		}
	}

	.image-wrapper {
		position: relative;
		width: 100%;
		height: 160px;
		background: var(--el-fill-color-light);

		.media-image {
			display: block;
			width: 100%;
			height: 100%;
			cursor: pointer;
		}

		.image-slot {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			height: 100%;
			color: var(--el-text-color-placeholder);
			font-size: 12px;
			gap: 4px;
		}

		.image-overlay {
			position: absolute;
			top: 8px;
			right: 8px;
			display: flex;
			gap: 6px;
			opacity: 0;
			transition: opacity 0.2s ease-in-out;
			z-index: 2;
		}
	}

	.media-meta {
		padding: 8px 10px;

		.media-title {
			display: flex;
			align-items: center;
			justify-content: space-between;
			margin-bottom: 4px;

			.title-left {
				display: flex;
				align-items: center;
				gap: 6px;
			}

			.badge {
				font-size: 11px;
			}

			.index-tag {
				font-size: 11px;
				color: var(--el-text-color-secondary);
				font-family: monospace;
			}
		}

		.media-subtitle {
			font-size: 12px;
			color: var(--el-text-color-regular);
			overflow: hidden;
			text-overflow: ellipsis;
			display: -webkit-box;
			-webkit-line-clamp: 2;
			-webkit-box-orient: vertical;
			line-height: 1.4;
		}
	}
}
</style>
