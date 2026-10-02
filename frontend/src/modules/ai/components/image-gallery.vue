<template>
	<div class="image-gallery-container">
		<!-- 1. 异步任务提交成功状态 -->
		<div v-if="taskSubmitted" class="task-result">
			<el-result
				icon="success"
				:title="$t('异步生图任务已提交')"
				:sub-title="`Task ID: ${taskSubmitted.taskId}`"
			>
				<template #extra>
					<div class="task-buttons">
						<el-button type="primary" @click="copyText(String(taskSubmitted.taskId))">
							<el-icon class="mr-2"><copy-document /></el-icon>
							{{ $t('复制任务 ID') }}
						</el-button>
						<el-button @click="navigateToTasks">
							{{ $t('前往任务列表') }}
						</el-button>
					</div>
				</template>
			</el-result>
		</div>

		<!-- 2. 生成中高亮加载态骨架屏 -->
		<div v-else-if="loading" class="generating-state">
			<div class="pulse-loader">
				<div class="spinner-ring"></div>
				<el-icon class="pulse-icon"><magic-stick /></el-icon>
			</div>
			<h3 class="generating-title">{{ $t('AI 正在绘制画面中...') }}</h3>
			<p class="generating-desc">{{ $t('正在调度算力与模型推理渲染，通常需要 3 ~ 15 秒，请稍候') }}</p>
			<div class="generating-skeleton-cards">
				<div v-for="n in count" :key="n" class="skeleton-card">
					<div class="shimmer-block"></div>
				</div>
			</div>
		</div>

		<!-- 3. 图片画廊网格 -->
		<div v-else-if="items.length" class="gallery-grid">
			<image-gallery-card
				v-for="(item, index) in items"
				:key="index"
				:item="item"
				:index="index"
				:preview-urls="previewUrls"
				:size="size"
				@download="downloadImage"
				@use-as-reference="src => $emit('use-as-reference', src)"
			/>
		</div>

		<!-- 4. 空状态提示 -->
		<div v-else class="empty-gallery">
			<div class="empty-graphic">
				<el-icon class="empty-icon"><picture-icon /></el-icon>
			</div>
			<h3 class="empty-title">{{ $t('等待生图指令') }}</h3>
			<p class="empty-desc">
				{{ $t('在左侧配置模型、输入提示词并调整尺寸后，点击「立即生成」即可在此处查看渲染成果。') }}
			</p>
			<el-button type="primary" plain @click="$emit('fill-sample')">
				<el-icon class="mr-2"><magic-stick /></el-icon>
				{{ $t('填入示例灵感试一试') }}
			</el-button>
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'image-gallery'
});

import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { CopyDocument, MagicStick, Picture as PictureIcon } from '@element-plus/icons-vue';
import ImageGalleryCard from './image-gallery-card.vue';

const { t } = useI18n();
const router = useRouter();

withDefaults(
	defineProps<{
		taskSubmitted?: any;
		loading?: boolean;
		items: Array<{ src: string; value: string; url?: string; b64?: string }>;
		previewUrls: string[];
		count?: number;
		size?: string;
	}>(),
	{
		taskSubmitted: null,
		loading: false,
		count: 1,
		size: 'Auto'
	}
);

defineEmits<{
	(e: 'use-as-reference', src: string): void;
	(e: 'fill-sample'): void;
}>();

async function copyText(val: string) {
	if (!val) return;
	try {
		await navigator.clipboard.writeText(val);
		ElMessage.success(t('已复制'));
	} catch {
		ElMessage.warning(t('复制失败'));
	}
}

function navigateToTasks() {
	router.push('/ai/task');
}

async function downloadImage(src: string, index: number) {
	try {
		const a = document.createElement('a');
		a.download = `ai-gen-${Date.now()}-${index + 1}.png`;

		if (src.startsWith('data:')) {
			a.href = src;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			ElMessage.success(t('下载已开始'));
			return;
		}

		const resp = await fetch(src);
		const blob = await resp.blob();
		const objectUrl = URL.createObjectURL(blob);
		a.href = objectUrl;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(objectUrl);
		ElMessage.success(t('下载已开始'));
	} catch (e) {
		window.open(src, '_blank');
	}
}
</script>

<style lang="scss" scoped>
.image-gallery-container {
	flex: 1;
	overflow-y: auto;
	padding: 16px;
	display: flex;
	flex-direction: column;
	background: var(--el-fill-color-extra-light);

	.task-result {
		margin: auto;
		background: var(--el-bg-color);
		padding: 30px 40px;
		border-radius: 12px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
		text-align: center;

		.task-buttons {
			display: flex;
			gap: 12px;
			justify-content: center;
			margin-top: 10px;
		}
	}

	.generating-state {
		margin: auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 32px 16px;
		text-align: center;
		width: 100%;
		max-width: 640px;

		.pulse-loader {
			position: relative;
			width: 64px;
			height: 64px;
			margin-bottom: 20px;
			display: flex;
			align-items: center;
			justify-content: center;

			.spinner-ring {
				position: absolute;
				inset: 0;
				border-radius: 50%;
				border: 3px solid transparent;
				border-top-color: var(--el-color-primary);
				border-right-color: var(--el-color-primary-light-3);
				animation: spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
			}

			.pulse-icon {
				font-size: 26px;
				color: var(--el-color-primary);
				animation: iconPulse 2s ease-in-out infinite;
			}
		}

		.generating-title {
			font-size: 17px;
			font-weight: 600;
			margin: 0 0 6px;
			color: var(--el-text-color-primary);
		}

		.generating-desc {
			font-size: 13px;
			color: var(--el-text-color-secondary);
			margin: 0 0 28px;
		}

		.generating-skeleton-cards {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
			gap: 14px;
			width: 100%;

			.skeleton-card {
				aspect-ratio: 1 / 1;
				background: var(--el-fill-color-darker);
				border-radius: 8px;
				overflow: hidden;
				position: relative;

				.shimmer-block {
					width: 100%;
					height: 100%;
					background: linear-gradient(
						90deg,
						rgba(255, 255, 255, 0) 0%,
						rgba(255, 255, 255, 0.08) 50%,
						rgba(255, 255, 255, 0) 100%
					);
					background-size: 200% 100%;
					animation: shimmer 1.8s infinite;
				}
			}
		}
	}

	.gallery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		gap: 14px;
		width: 100%;
	}

	.empty-gallery {
		margin: auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 40px 20px;
		text-align: center;
		max-width: 420px;

		.empty-graphic {
			width: 72px;
			height: 72px;
			border-radius: 20px;
			background: var(--el-fill-color);
			display: flex;
			align-items: center;
			justify-content: center;
			margin-bottom: 16px;

			.empty-icon {
				font-size: 34px;
				color: var(--el-text-color-placeholder);
			}
		}

		.empty-title {
			font-size: 16px;
			font-weight: 600;
			margin: 0 0 6px;
			color: var(--el-text-color-primary);
		}

		.empty-desc {
			font-size: 13px;
			color: var(--el-text-color-secondary);
			line-height: 1.5;
			margin: 0 0 20px;
		}
	}
}

@keyframes spin {
	to {
		transform: rotate(360deg);
	}
}

@keyframes iconPulse {
	0%,
	100% {
		transform: scale(0.9);
		opacity: 0.8;
	}
	50% {
		transform: scale(1.1);
		opacity: 1;
	}
}

@keyframes shimmer {
	0% {
		background-position: -200% 0;
	}
	100% {
		background-position: 200% 0;
	}
}
</style>
