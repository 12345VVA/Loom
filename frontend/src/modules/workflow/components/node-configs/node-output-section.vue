<template>
	<div class="output-section">
		<div class="output-header">
			<div class="output-title">
				<el-icon class="arrow-icon"><arrow-down /></el-icon>
				{{ title || $t('输出') }}
				<el-tooltip v-if="tooltip" placement="top" effect="dark" :content="tooltip">
					<el-icon class="hint-icon"><warning /></el-icon>
				</el-tooltip>
			</div>

			<div class="output-actions">
				<slot name="actions"></slot>
			</div>
		</div>

		<div class="output-content">
			<slot></slot>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ArrowDown, Warning } from '@element-plus/icons-vue';

defineProps<{
	title?: string;
	tooltip?: string;
}>();
</script>

<style lang="scss" scoped>
.output-section {
	border-top: 1px solid var(--el-border-color-lighter);
	margin-top: 16px;
	padding-top: 12px;
	margin-bottom: 18px;

	.output-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 12px;

		.output-title {
			display: flex;
			align-items: center;
			font-size: 13px;
			font-weight: 600;
			color: var(--el-text-color-primary);

			.arrow-icon {
				margin-right: 4px;
				font-size: 12px;
				color: var(--el-text-color-secondary);
			}

			.hint-icon {
				margin-left: 6px;
				font-size: 12px;
				color: var(--el-text-color-placeholder);
				cursor: help;
			}
		}

		.output-actions {
			display: flex;
			align-items: center;

			:deep(.json-actions-divider) {
				width: 1px;
				height: 14px;
				background-color: var(--el-border-color);
				margin: 0 8px;
			}

			:deep(.action-icon-btn) {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 24px;
				height: 24px;
				border-radius: 4px;
				color: var(--el-text-color-secondary);
				cursor: pointer;
				transition:
					background-color 0.2s,
					color 0.2s;
				margin-left: 2px;

				&:hover {
					background-color: var(--el-fill-color-light);
					color: var(--el-color-primary);
				}

				&.primary {
					color: var(--el-color-primary);
					background-color: var(--el-color-primary-light-9);
					&:hover {
						background-color: var(--el-color-primary-light-8);
					}
				}

				.el-icon {
					font-size: 14px;
				}
			}

			:deep(.output-format-btn) {
				display: inline-flex;
				align-items: center;
				padding: 2px 8px;
				font-size: 12px;
				color: var(--el-color-primary);
				background-color: var(--el-color-primary-light-9);
				border-radius: 4px;
				cursor: pointer;
				transition: background-color 0.2s;
				user-select: none;

				&:hover {
					background-color: var(--el-color-primary-light-8);
				}

				.el-icon {
					font-size: 12px;
				}
			}
		}
	}
}
</style>
