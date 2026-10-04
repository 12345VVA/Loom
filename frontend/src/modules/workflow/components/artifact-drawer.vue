<template>
	<!--
		工作流实例产物抽屉：图片画廊 + 文本/JSON 结构化卡片。
		数据来自成功终态落地的 workflow_artifact（与执行日志/快照解耦）。
	-->
	<el-drawer
		:model-value="visible"
		:size="drawerSize"
		:with-header="false"
		destroy-on-close
		class="artifact-drawer"
		@update:model-value="(v: boolean) => emit('update:visible', v)"
		@close="handleClose"
	>
		<div class="artifact-drawer-layout" v-loading="loading">
			<!-- 顶部导航栏 -->
			<header class="artifact-header">
				<div class="header-left">
					<div class="header-icon-box">
						<svg class="header-svg" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
							<polyline points="3.27 6.96 12 12.01 20.73 6.96" />
							<line x1="12" y1="22.08" x2="12" y2="12" />
						</svg>
					</div>
					<div class="header-titles">
						<div class="title-row">
							<span class="main-title">{{ $t('实例产物') }}</span>
							<el-tag size="small" type="primary" effect="light" round>
								#{{ instanceId }}
							</el-tag>
						</div>
						<span class="sub-title">{{ $t('工作流最终输出落地成果（图片/文本/结构化数据）') }}</span>
					</div>
				</div>

				<div class="header-actions">
					<!-- 一键打包下载全部图片 -->
					<el-button
						v-if="imageItems.length > 0"
						type="primary"
						size="default"
						:loading="downloadingZip"
						@click="handleDownloadAllImages"
					>
						<template #icon>
							<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
								<polyline points="7 10 12 15 17 10" />
								<line x1="12" y1="15" x2="12" y2="3" />
							</svg>
						</template>
						{{ downloadingZip ? (downloadProgressText || $t('打包中...')) : $t('打包下载全部图片') }}
						<span class="badge-count">({{ imageItems.length }})</span>
					</el-button>

					<!-- 切换全屏 -->
					<button class="tool-icon-btn" :title="isFullscreen ? $t('还原宽度') : $t('全屏展示')" @click="isFullscreen = !isFullscreen">
						<svg v-if="!isFullscreen" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
						</svg>
						<svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M4 14h6v6m10-10h-6V4m0 16v-6h6M10 4v6H4" />
						</svg>
					</button>

					<!-- 关闭按钮 -->
					<button class="tool-icon-btn close-btn" :title="$t('关闭')" @click="handleClose">
						<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
							<line x1="18" y1="6" x2="6" y2="18" />
							<line x1="6" y1="6" x2="18" y2="18" />
						</svg>
					</button>
				</div>
			</header>

			<!-- 统计状态胶囊栏 -->
			<div v-if="items.length > 0" class="artifact-summary-bar">
				<div class="summary-pill total">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
						<polygon points="12 2 2 7 12 12 22 7 12 2" />
						<polyline points="2 17 12 22 22 17" />
						<polyline points="2 12 12 17 22 12" />
					</svg>
					<span>{{ $t('产物总计') }}</span>
					<strong>{{ items.length }}</strong>
				</div>
				<div v-if="imageItems.length > 0" class="summary-pill image">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
						<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
						<circle cx="8.5" cy="8.5" r="1.5" />
						<polyline points="21 15 16 10 5 21" />
					</svg>
					<span>{{ $t('图片产物') }}</span>
					<strong>{{ imageItems.length }}</strong>
				</div>
				<div v-if="textItems.length > 0" class="summary-pill text">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
						<polyline points="14 2 14 8 20 8" />
						<line x1="16" y1="13" x2="8" y2="13" />
						<line x1="16" y1="17" x2="8" y2="17" />
					</svg>
					<span>{{ $t('文本/数据') }}</span>
					<strong>{{ textItems.length }}</strong>
				</div>
			</div>

			<!-- 主体内容区域 -->
			<div class="artifact-body">
				<template v-if="items.length > 0">
					<!-- 图片画廊区域 -->
					<section v-if="imageItems.length > 0" class="artifact-section">
						<div class="section-title-bar">
							<div class="title-with-icon">
								<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
									<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
									<circle cx="8.5" cy="8.5" r="1.5" />
									<polyline points="21 15 16 10 5 21" />
								</svg>
								<span class="title-text">{{ $t('图片画廊') }}</span>
								<span class="count-tag">{{ imageItems.length }}</span>
							</div>
							<div class="section-actions">
								<el-button link type="primary" size="small" @click="copyAllImageUrls">
									<template #icon>
										<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
											<rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
											<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
										</svg>
									</template>
									{{ $t('复制全部链接') }}
								</el-button>
							</div>
						</div>

						<div class="artifact-image-grid">
							<div v-for="(item, index) in imageItems" :key="item.id" class="artifact-image-card">
								<div class="image-wrapper">
									<el-image
										class="artifact-img"
										:src="item.src"
										fit="contain"
										:preview-src-list="previewUrls"
										:initial-index="index"
										preview-teleported
										loading="lazy"
									>
										<template #placeholder>
											<div class="image-loading-placeholder">
												<div class="pulse-skeleton"></div>
											</div>
										</template>
										<template #error>
											<div class="image-error-placeholder">
												<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5">
													<circle cx="12" cy="12" r="10" />
													<line x1="12" y1="8" x2="12" y2="12" />
													<line x1="12" y1="16" x2="12.01" y2="16" />
												</svg>
												<span>{{ $t('加载失败') }}</span>
											</div>
										</template>
									</el-image>
									<span class="index-badge">#{{ index + 1 }}</span>
								</div>

								<div class="card-footer">
									<div class="field-meta" :title="item.fieldPath || item.fieldKey">
										<span class="field-key">{{ item.fieldKey }}</span>
										<span v-if="item.fieldPath" class="field-path">{{ item.fieldPath }}</span>
									</div>
									<div class="card-btn-group">
										<button class="action-btn" :title="$t('复制原图链接')" @click="copyValue(item.copyText)">
											<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
												<rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
												<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
											</svg>
										</button>
										<button class="action-btn primary" :title="$t('下载此图')" @click="downloadSingle(item, index)">
											<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
												<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
												<polyline points="7 10 12 15 17 10" />
												<line x1="12" y1="15" x2="12" y2="3" />
											</svg>
										</button>
									</div>
								</div>
							</div>
						</div>
					</section>

					<!-- 文本与结构化产物区域 -->
					<section v-if="textItems.length > 0" class="artifact-section">
						<div class="section-title-bar">
							<div class="title-with-icon">
								<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
									<polyline points="14 2 14 8 20 8" />
									<line x1="16" y1="13" x2="8" y2="13" />
									<line x1="16" y1="17" x2="8" y2="17" />
								</svg>
								<span class="title-text">{{ $t('文本与结构化数据') }}</span>
								<span class="count-tag">{{ textItems.length }}</span>
							</div>
						</div>

						<div class="artifact-text-list">
							<div v-for="item in textItems" :key="item.id" class="artifact-text-card">
								<div class="card-header">
									<div class="header-key-area">
										<span class="key-name">{{ item.fieldKey }}</span>
										<span v-if="item.fieldPath" class="path-badge">{{ item.fieldPath }}</span>
										<el-tag size="small" :type="item.assetType === 'json' ? 'warning' : 'info'" effect="plain">
											{{ item.assetType.toUpperCase() }}
										</el-tag>
									</div>
									<el-button link type="primary" size="small" @click="copyValue(item.copyText)">
										<template #icon>
											<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
												<rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
												<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
											</svg>
										</template>
										{{ $t('复制内容') }}
									</el-button>
								</div>
								<div class="card-content-wrap">
									<pre class="content-pre">{{ item.display }}</pre>
								</div>
							</div>
						</div>
					</section>
				</template>

				<!-- 空状态 -->
				<div v-else-if="!loading" class="artifact-empty">
					<div class="empty-icon-wrap">
						<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.2">
							<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
							<polyline points="3.27 6.96 12 12.01 20.73 6.96" />
							<line x1="12" y1="22.08" x2="12" y2="12" />
						</svg>
					</div>
					<h3 class="empty-title">{{ $t('该实例暂无产物') }}</h3>
					<p class="empty-desc">{{ $t('当工作流运行到成功终态并且 end 节点配置了输出字段时，产物将自动落库并在此展示。') }}</p>
				</div>
			</div>
		</div>
	</el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { copyToClipboard, formatJson } from '../utils';
import { useAssetUrl } from '/$/media';
import { downloadSingleImage, downloadImagesAsZip } from '../utils/download';

defineOptions({ name: 'workflow-artifact-drawer' });

const props = defineProps<{
	visible: boolean;
	instanceId?: number;
	size?: string;
}>();

const emit = defineEmits<{
	(e: 'update:visible', v: boolean): void;
	(e: 'close'): void;
}>();

const { service } = useCool();
const { t } = useI18n();
const { assetUrl, ensureDownloadToken } = useAssetUrl();

const isFullscreen = ref(false);
const drawerSize = computed(() => {
	if (isFullscreen.value) return '100vw';
	return props.size || '720px';
});

interface ArtifactItem {
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

const loading = ref(false);
const items = ref<ArtifactItem[]>([]);
const downloadingZip = ref(false);
const downloadProgressText = ref('');

watch(
	() => [props.visible, props.instanceId],
	([visible, instId]) => {
		if (visible && instId) {
			fetchArtifacts(Number(instId));
		}
	},
	{ immediate: true }
);

async function fetchArtifacts(instanceId: number) {
	loading.value = true;
	items.value = [];
	try {
		await ensureDownloadToken();
		const res = await (service as any).workflow.artifact.page({
			instanceId,
			page: 1,
			size: 500
		});
		// 核心关键修复：CoolAdmin 标准分页接口返回的是 res.list，并兼容部分环境下的 res.items
		items.value = res?.list || res?.items || [];
	} catch (err: any) {
		ElMessage.error(t('获取产物失败: ') + (err.message || err));
	} finally {
		loading.value = false;
	}
}

function handleClose() {
	emit('update:visible', false);
	emit('close');
}

interface DisplayItem {
	id: number;
	fieldKey: string;
	fieldPath?: string;
	assetType: string;
	src: string;
	copyText: string;
	display: string;
}

function isLikelyImageUrl(str: string): boolean {
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

function findImagesInData(data: any, prefix = ''): Array<{ url: string; path: string }> {
	const list: Array<{ url: string; path: string }> = [];
	if (!data) return list;

	function walk(val: any, currentPath: string) {
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

const displayItems = computed(() => {
	const result: DisplayItem[] = [];
	// 图片按原始 URL 全程去重：后端图片产物与 json 产物（内嵌图片探测）并存、以及
	// 循环快照重复携带外层图片时，同一 URL 只展示/打包一张
	const seenImageUrls = new Set<string>();

	items.value.forEach(item => {
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
				const parsed = JSON.parse(raw);
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
});
const imageItems = computed(() => displayItems.value.filter(i => i.assetType === 'image' && i.src));
const textItems = computed(() => displayItems.value.filter(i => i.assetType !== 'image'));
const previewUrls = computed(() => imageItems.value.map(i => i.src));

async function copyValue(value: string) {
	await copyToClipboard(value);
	ElMessage.success(t('已复制'));
}

function copyAllImageUrls() {
	if (imageItems.value.length === 0) return;
	const text = imageItems.value.map(i => i.copyText).join('\n');
	copyToClipboard(text, t('已复制全部图片链接'), t('复制失败'));
}

async function handleDownloadAllImages() {
	if (imageItems.value.length === 0) {
		ElMessage.warning(t('暂无图片可下载'));
		return;
	}
	downloadingZip.value = true;
	downloadProgressText.value = '';
	try {
		const itemsToDownload = imageItems.value.map((img, idx) => ({
			url: img.src || img.copyText,
			title: img.fieldKey,
			subtitle: img.fieldPath || `${img.fieldKey}_${idx + 1}`
		}));
		const zipName = `instance_${props.instanceId}_artifacts_${Date.now()}.zip`;
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

function downloadSingle(item: DisplayItem, index: number) {
	const name = item.fieldPath || item.fieldKey || `image_${index + 1}`;
	const cleanUrl = item.copyText.split('?')[0];
	const extMatch = cleanUrl.match(/\.(png|jpe?g|webp|gif|svg)$/i);
	const ext = extMatch ? extMatch[0].toLowerCase() : '.png';
	downloadSingleImage(item.src || item.copyText, `${name}${ext}`);
}
</script>

<style lang="scss" scoped>
.artifact-drawer {
	:deep(.el-drawer__body) {
		padding: 0;
		background: #f8fafc;
	}
}

.artifact-drawer-layout {
	display: flex;
	flex-direction: column;
	height: 100vh;
	background: #f8fafc;
}

/* 顶部 Header */
.artifact-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 14px 20px;
	background: #ffffff;
	border-bottom: 1px solid #e2e8f0;
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
	z-index: 10;

	.header-left {
		display: flex;
		align-items: center;
		gap: 12px;

		.header-icon-box {
			display: flex;
			align-items: center;
			justify-content: center;
			width: 38px;
			height: 38px;
			border-radius: 10px;
			background: linear-gradient(135deg, #e0e7ff 0%, #ede9fe 100%);
			color: #4f46e5;
		}

		.header-titles {
			display: flex;
			flex-direction: column;

			.title-row {
				display: flex;
				align-items: center;
				gap: 8px;

				.main-title {
					font-size: 16px;
					font-weight: 600;
					color: #0f172a;
				}
			}

			.sub-title {
				font-size: 12px;
				color: #64748b;
				margin-top: 2px;
			}
		}
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 10px;

		.badge-count {
			margin-left: 4px;
			opacity: 0.85;
			font-size: 12px;
		}

		.tool-icon-btn {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			width: 32px;
			height: 32px;
			border-radius: 6px;
			border: 1px solid #e2e8f0;
			background: #ffffff;
			color: #475569;
			cursor: pointer;
			transition: all 0.2s ease;

			&:hover {
				background: #f1f5f9;
				color: #0f172a;
				border-color: #cbd5e1;
			}

			&.close-btn:hover {
				background: #fee2e2;
				color: #ef4444;
				border-color: #fca5a5;
			}
		}
	}
}

/* 汇总统计胶囊栏 */
.artifact-summary-bar {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 10px 20px;
	background: #ffffff;
	border-bottom: 1px solid #f1f5f9;

	.summary-pill {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 4px 10px;
		border-radius: 20px;
		font-size: 12px;

		strong {
			font-weight: 700;
		}

		&.total {
			background: #f1f5f9;
			color: #334155;
		}

		&.image {
			background: #e0e7ff;
			color: #4338ca;
		}

		&.text {
			background: #fef3c7;
			color: #b45309;
		}
	}
}

/* 主体容器 */
.artifact-body {
	flex: 1;
	overflow-y: auto;
	padding: 16px 20px;
	display: flex;
	flex-direction: column;
	gap: 20px;
}

.artifact-section {
	display: flex;
	flex-direction: column;
	gap: 12px;

	.section-title-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;

		.title-with-icon {
			display: flex;
			align-items: center;
			gap: 8px;
			color: #1e293b;

			.title-text {
				font-size: 14px;
				font-weight: 600;
			}

			.count-tag {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				height: 18px;
				padding: 0 6px;
				border-radius: 9px;
				background: #e2e8f0;
				color: #475569;
				font-size: 11px;
				font-weight: 600;
			}
		}
	}
}

/* 图片画廊 Grid */
.artifact-image-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
	gap: 14px;

	.artifact-image-card {
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 10px;
		overflow: hidden;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
		transition: transform 0.2s, box-shadow 0.2s;

		&:hover {
			transform: translateY(-2px);
			box-shadow: 0 6px 12px rgba(0, 0, 0, 0.08);
			border-color: #cbd5e1;
		}

		.image-wrapper {
			position: relative;
			width: 100%;
			height: 190px;
			background: #f8fafc;
			overflow: hidden;

			.artifact-img {
				width: 100%;
				height: 100%;
				display: block;
			}

			.index-badge {
				position: absolute;
				top: 8px;
				left: 8px;
				background: rgba(15, 23, 42, 0.65);
				color: #ffffff;
				font-size: 11px;
				font-weight: 600;
				padding: 2px 6px;
				border-radius: 4px;
				backdrop-filter: blur(4px);
			}

			.image-loading-placeholder {
				width: 100%;
				height: 100%;
				background: #f1f5f9;
			}

			.image-error-placeholder {
				width: 100%;
				height: 100%;
				display: flex;
				flex-direction: column;
				align-items: center;
				justify-content: center;
				gap: 6px;
				color: #94a3b8;
				font-size: 12px;
			}
		}

		.card-footer {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 8px 10px;
			background: #ffffff;
			border-top: 1px solid #f1f5f9;

			.field-meta {
				flex: 1;
				min-width: 0;
				display: flex;
				flex-direction: column;

				.field-key {
					font-size: 12px;
					font-weight: 600;
					color: #334155;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}

				.field-path {
					font-size: 11px;
					color: #94a3b8;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}
			}

			.card-btn-group {
				display: flex;
				align-items: center;
				gap: 4px;

				.action-btn {
					display: inline-flex;
					align-items: center;
					justify-content: center;
					width: 26px;
					height: 26px;
					border-radius: 4px;
					border: 1px solid #e2e8f0;
					background: #f8fafc;
					color: #475569;
					cursor: pointer;
					transition: all 0.15s;

					&:hover {
						background: #e2e8f0;
						color: #0f172a;
					}

					&.primary:hover {
						background: #4f46e5;
						color: #ffffff;
						border-color: #4f46e5;
					}
				}
			}
		}
	}
}

/* 文本卡片列表 */
.artifact-text-list {
	display: flex;
	flex-direction: column;
	gap: 12px;

	.artifact-text-card {
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 10px;
		overflow: hidden;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);

		.card-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 10px 14px;
			background: #f8fafc;
			border-bottom: 1px solid #e2e8f0;

			.header-key-area {
				display: flex;
				align-items: center;
				gap: 8px;

				.key-name {
					font-size: 13px;
					font-weight: 600;
					color: #1e293b;
				}

				.path-badge {
					font-size: 11px;
					padding: 2px 6px;
					border-radius: 4px;
					background: #e2e8f0;
					color: #475569;
					font-family: monospace;
				}
			}
		}

		.card-content-wrap {
			padding: 12px 14px;

			.content-pre {
				margin: 0;
				font-family: 'Fira Code', 'Consolas', monospace;
				font-size: 12px;
				line-height: 1.6;
				color: #334155;
				background: #f8fafc;
				padding: 10px 12px;
				border-radius: 6px;
				border: 1px solid #f1f5f9;
				max-height: 320px;
				overflow-y: auto;
				white-space: pre-wrap;
				word-break: break-all;
			}
		}
	}
}

/* 空状态 */
.artifact-empty {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 80px 20px;
	color: #94a3b8;
	text-align: center;

	.empty-icon-wrap {
		width: 72px;
		height: 72px;
		border-radius: 50%;
		background: #f1f5f9;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #94a3b8;
		margin-bottom: 16px;
	}

	.empty-title {
		font-size: 15px;
		font-weight: 600;
		color: #475569;
		margin: 0 0 6px 0;
	}

	.empty-desc {
		font-size: 12px;
		color: #94a3b8;
		max-width: 360px;
		line-height: 1.6;
		margin: 0;
	}
}
</style>
