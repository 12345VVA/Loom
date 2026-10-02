<template>
	<aside v-if="visible" class="ai-stream-drawer">
		<header class="stream-header">
			<div class="stream-title-group">
				<el-icon class="stream-icon"><data-analysis /></el-icon>
				<strong>{{ title || $t('SSE 实时流审计') }}</strong>
				<el-tag v-if="status" size="small" :type="statusType">
					{{ status }}
				</el-tag>
			</div>
			<div class="stream-header-tools">
				<el-button link size="small" @click="$emit('clear')">
					{{ $t('清空') }}
				</el-button>
				<el-button link size="small" @click="$emit('copy')">
					{{ $t('复制全部') }}
				</el-button>
				<el-icon class="drawer-close" @click="closeDrawer">
					<close />
				</el-icon>
			</div>
		</header>

		<div class="stream-list">
			<div
				v-for="(item, index) in events"
				:key="index"
				class="stream-event-card"
				:class="item.event"
			>
				<div class="event-meta">
					<span class="event-tag">{{ item.event || 'message' }}</span>
					<span class="event-seq">#{{ index + 1 }}</span>
				</div>
				<pre class="event-body">{{ formatEvent(item) }}</pre>
			</div>

			<div v-if="!events.length" class="empty-stream">
				<el-icon><connection /></el-icon>
				<span>{{ $t('暂无实时流事件') }}</span>
				<p>{{ $t('使用「流式发送」时，后端分块事件将实时在此展示') }}</p>
			</div>
		</div>
	</aside>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-stream-drawer'
});

import { computed } from 'vue';
import { DataAnalysis, Close, Connection } from '@element-plus/icons-vue';

interface StreamEventItem {
	event?: string;
	data?: any;
	[key: string]: any;
}

const props = withDefaults(
	defineProps<{
		modelValue: boolean;
		events: StreamEventItem[];
		status?: string;
		statusType?: 'success' | 'warning' | 'info' | 'primary' | 'danger';
		title?: string;
	}>(),
	{
		status: '',
		statusType: 'info',
		title: ''
	}
);

const emit = defineEmits<{
	(e: 'update:modelValue', value: boolean): void;
	(e: 'clear'): void;
	(e: 'copy'): void;
}>();

const visible = computed({
	get: () => props.modelValue,
	set: val => emit('update:modelValue', val)
});

function closeDrawer() {
	visible.value = false;
}

function formatEvent(item: StreamEventItem): string {
	if (typeof item.data === 'object') {
		return JSON.stringify(item.data, null, 2);
	}
	return String(item.data || '');
}
</script>

<style lang="scss" scoped>
.ai-stream-drawer {
	width: 380px;
	height: 100%;
	display: flex;
	flex-direction: column;
	background: var(--el-bg-color);
	border-left: 1px solid var(--el-border-color-light);
	box-shadow: -4px 0 16px rgba(0, 0, 0, 0.05);
	flex-shrink: 0;
	z-index: 10;
	animation: slideInRight 0.22s ease-out;

	.stream-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 16px;
		background: var(--el-fill-color-light);
		border-bottom: 1px solid var(--el-border-color-lighter);
		flex-shrink: 0;

		.stream-title-group {
			display: flex;
			align-items: center;
			gap: 8px;

			.stream-icon {
				font-size: 16px;
				color: var(--el-color-primary);
			}

			strong {
				font-size: 14px;
				font-weight: 600;
				color: var(--el-text-color-primary);
			}
		}

		.stream-header-tools {
			display: flex;
			align-items: center;
			gap: 6px;

			.drawer-close {
				font-size: 16px;
				cursor: pointer;
				color: var(--el-text-color-secondary);
				margin-left: 4px;
				transition: color 0.15s;

				&:hover {
					color: var(--el-color-danger);
				}
			}
		}
	}

	.stream-list {
		flex: 1;
		overflow-y: auto;
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		background: var(--el-fill-color-extra-light);

		.stream-event-card {
			background: var(--el-bg-color);
			border: 1px solid var(--el-border-color-lighter);
			border-left: 3px solid var(--el-color-primary);
			border-radius: 6px;
			padding: 8px 10px;
			font-size: 12px;

			&.error {
				border-left-color: var(--el-color-danger);
			}
			&.done {
				border-left-color: var(--el-color-success);
			}

			.event-meta {
				display: flex;
				justify-content: space-between;
				align-items: center;
				margin-bottom: 4px;

				.event-tag {
					font-weight: 600;
					color: var(--el-text-color-primary);
					text-transform: uppercase;
					font-size: 11px;
				}

				.event-seq {
					color: var(--el-text-color-secondary);
					font-size: 11px;
				}
			}

			.event-body {
				margin: 0;
				white-space: pre-wrap;
				word-break: break-all;
				font-family: monospace;
				color: var(--el-text-color-regular);
				font-size: 11.5px;
				line-height: 1.4;
			}
		}

		.empty-stream {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			padding: 48px 16px;
			color: var(--el-text-color-secondary);
			text-align: center;

			.el-icon {
				font-size: 32px;
				margin-bottom: 8px;
				opacity: 0.5;
			}

			span {
				font-size: 14px;
				font-weight: 500;
			}

			p {
				margin: 4px 0 0;
				font-size: 12px;
				opacity: 0.8;
			}
		}
	}
}

@keyframes slideInRight {
	from {
		transform: translateX(100%);
		opacity: 0;
	}
	to {
		transform: translateX(0);
		opacity: 1;
	}
}
</style>
