<template>
	<div class="gallery-card">
		<div class="image-wrapper">
			<el-image
				class="gallery-image"
				:src="item.src"
				fit="contain"
				:preview-src-list="previewUrls"
				:initial-index="index"
				preview-teleported
				loading="lazy"
			>
				<template #placeholder>
					<div class="image-loading-placeholder">
						<el-icon class="is-loading"><refresh /></el-icon>
						<span>{{ $t('加载图像中...') }}</span>
					</div>
				</template>
				<template #error>
					<div class="image-error-placeholder">
						<el-icon><picture-icon /></el-icon>
						<span>{{ $t('图片加载失败') }}</span>
					</div>
				</template>
			</el-image>

			<!-- 悬浮操作栏 (底部半透明磨砂) -->
			<div class="image-hover-overlay">
				<el-tooltip :content="$t('大图全屏预览')" placement="top">
					<button
						type="button"
						class="action-icon-btn"
						@click.stop="triggerPreview"
					>
						<el-icon><zoom-in /></el-icon>
					</button>
				</el-tooltip>

				<el-tooltip :content="$t('下载原图到本地')" placement="top">
					<button
						type="button"
						class="action-icon-btn"
						@click.stop="$emit('download', item.src, index)"
					>
						<el-icon><download /></el-icon>
					</button>
				</el-tooltip>

				<el-tooltip :content="$t('复制图片地址')" placement="top">
					<button
						type="button"
						class="action-icon-btn"
						@click.stop="copyText(item.value)"
					>
						<el-icon><copy-document /></el-icon>
					</button>
				</el-tooltip>

				<el-tooltip :content="$t('设为参考图 (图生图)')" placement="top">
					<button
						type="button"
						class="action-icon-btn"
						@click.stop="$emit('use-as-reference', item.src)"
					>
						<el-icon><connection /></el-icon>
					</button>
				</el-tooltip>

				<el-tooltip v-if="item.url" :content="$t('新标签页打开')" placement="top">
					<button
						type="button"
						class="action-icon-btn"
						@click.stop="openUrl(item.url)"
					>
						<el-icon><top-right /></el-icon>
					</button>
				</el-tooltip>
			</div>
		</div>

		<div class="card-caption">
			<span class="index-num">#{{ index + 1 }}</span>
			<span class="format-tag">{{ size || 'Auto' }}</span>
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'image-gallery-card'
});

import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import {
	Refresh,
	Picture as PictureIcon,
	ZoomIn,
	Download,
	CopyDocument,
	Connection,
	TopRight
} from '@element-plus/icons-vue';

const { t } = useI18n();

const props = withDefaults(
	defineProps<{
		item: {
			src: string;
			value: string;
			url?: string;
			b64?: string;
		};
		index: number;
		previewUrls: string[];
		size?: string;
	}>(),
	{
		size: 'Auto'
	}
);

defineEmits<{
	(e: 'download', src: string, index: number): void;
	(e: 'use-as-reference', src: string): void;
}>();

function triggerPreview() {
	const imgs = document.querySelectorAll<HTMLElement>('.gallery-image img');
	if (imgs[props.index]) {
		imgs[props.index].click();
	}
}

async function copyText(val: string) {
	if (!val) return;
	try {
		await navigator.clipboard.writeText(val);
		ElMessage.success(t('已复制图片地址'));
	} catch {
		ElMessage.warning(t('复制失败'));
	}
}

function openUrl(url: string) {
	if (url) {
		window.open(url, '_blank');
	}
}
</script>

<style lang="scss" scoped>
.gallery-card {
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	overflow: hidden;
	display: flex;
	flex-direction: column;
	transition: all 0.22s ease-out;

	&:hover {
		border-color: var(--el-color-primary-light-5);
		box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
		transform: translateY(-2px);

		.image-hover-overlay {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.image-wrapper {
		position: relative;
		width: 100%;
		aspect-ratio: 1 / 1;
		background: var(--el-fill-color-darker);
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;

		.gallery-image {
			width: 100%;
			height: 100%;
			display: block;

			:deep(img) {
				object-fit: contain;
			}
		}

		.image-loading-placeholder,
		.image-error-placeholder {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			gap: 6px;
			color: #94a3b8;
			font-size: 12px;
			height: 100%;

			.el-icon {
				font-size: 20px;
			}
		}

		.image-hover-overlay {
			position: absolute;
			bottom: 0;
			left: 0;
			right: 0;
			padding: 8px 10px;
			background: linear-gradient(to top, rgba(15, 23, 42, 0.75), transparent);
			backdrop-filter: blur(4px);
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 8px;
			opacity: 0;
			transform: translateY(8px);
			transition: all 0.2s ease-out;

			.action-icon-btn {
				background: rgba(255, 255, 255, 0.2);
				border: 1px solid rgba(255, 255, 255, 0.3);
				color: #ffffff;
				width: 30px;
				height: 30px;
				border-radius: 6px;
				display: flex;
				align-items: center;
				justify-content: center;
				cursor: pointer;
				font-size: 14px;
				transition: all 0.15s;

				&:hover {
					background: var(--el-color-primary);
					border-color: var(--el-color-primary);
					transform: scale(1.08);
				}
			}
		}
	}

	.card-caption {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 6px 10px;
		background: var(--el-fill-color-blank);
		border-top: 1px solid var(--el-border-color-lighter);
		font-size: 11.5px;

		.index-num {
			font-weight: 600;
			color: var(--el-text-color-primary);
		}

		.format-tag {
			color: var(--el-text-color-secondary);
			font-family: monospace;
			font-size: 10.5px;
		}
	}
}
</style>
