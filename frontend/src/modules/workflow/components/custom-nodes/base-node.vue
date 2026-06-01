<template>
	<div class="custom-flow-node-wrapper">
		<div class="custom-flow-node" :class="[nodeClass, { 'is-selected': selected, 'is-child': isChild }]">
			<handle v-if="hasTarget" type="target" :position="Position.Left" />
			<el-icon class="node-icon">
				<component :is="icon" />
			</el-icon>
			<span class="node-label">{{ label }}</span>
			<span v-if="isChild" class="child-badge">{{ groupLabel }}</span>
			<span v-if="incomplete" class="node-incomplete-dot" />
			<handle v-if="hasSource" type="source" :position="Position.Right" />
		</div>
		
		<!-- 节点下方的执行日志展示 -->
		<div v-if="runLog" class="node-run-log" :class="'status-' + runLog.status">
			<!-- 头部状态栏 -->
			<div class="log-header" @click="isLogExpanded = !isLogExpanded">
				<div class="log-status">
					<el-icon v-if="runLog.status === 'success'" color="#67c23a"><CircleCheckFilled /></el-icon>
					<el-icon v-else-if="runLog.status === 'error'" color="#f56c6c"><CircleCloseFilled /></el-icon>
					<el-icon v-else-if="runLog.status === 'running'" class="is-loading" color="#409eff"><Loading /></el-icon>
					<el-icon v-else color="#909399"><InfoFilled /></el-icon>
					
					<span class="status-text" v-if="runLog">
						{{ statusText }}
					</span>
					<span v-if="runLog.timeCost" class="time-cost">{{ runLog.timeCost }}ms</span>
				</div>
				<el-icon class="expand-icon"><ArrowDown v-if="isLogExpanded" /><ArrowRight v-else /></el-icon>
			</div>
			
			<div v-show="isLogExpanded" class="log-body">
				<div v-if="runLog.inputData" class="log-section">
					<div class="log-title">
						<span>{{ $t('输入') }}</span>
						<el-icon class="copy-btn" @click.stop="copyToClipboard(formatJson(runLog.inputData))"><CopyDocument /></el-icon>
					</div>
					<div class="log-content">{{ formatJson(runLog.inputData) }}</div>
				</div>
				<div v-if="runLog.outputData" class="log-section">
					<div class="log-title">
						<span>{{ $t('输出') }}</span>
						<el-icon class="copy-btn" @click.stop="copyToClipboard(formatJson(runLog.outputData))"><CopyDocument /></el-icon>
					</div>
					<div class="log-content">{{ formatJson(runLog.outputData) }}</div>
				</div>
				<div v-if="!runLog.inputData && !runLog.outputData" class="log-empty">
					{{ $t('本次运行暂无数据') }}
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Handle, Position, useNode } from '@vue-flow/core';
import { computed, ref } from 'vue';
import { CircleCheckFilled, CircleCloseFilled, Loading, InfoFilled, ArrowDown, ArrowRight, CopyDocument } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';
import { formatJson, copyToClipboard } from '../../utils';

const { t } = useI18n();

const props = defineProps<{
	label: string;
	selected?: boolean;
	icon: any;
	nodeClass: string;
	hasTarget?: boolean;
	hasSource?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	incomplete?: boolean;
}>();

const { node } = useNode();
const runLog = computed(() => node.data?.runLog);
const isLogExpanded = ref(true);

const statusText = computed(() => {
	const s = runLog.value?.status;
	if (s === 'success') return t('运行成功');
	if (s === 'error') return t('运行失败');
	if (s === 'running') return t('试运行中...');
	return t('准备中');
});
</script>

<style lang="scss" scoped>
.custom-flow-node {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 10px 16px;
	background-color: #ffffff;
	border: 1px solid var(--el-border-color);
	border-radius: 8px;
	box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
	font-size: 13px;
	font-weight: 500;
	color: var(--el-text-color-primary);
	min-width: 150px;
	height: 42px;
	box-sizing: border-box;
	transition: all 0.2s ease-in-out;
	position: relative;

	&:hover {
		box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
	}

	&.is-selected {
		border-color: var(--el-color-primary);
		box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2), 0 4px 12px rgba(64, 158, 255, 0.1);
	}

	&.is-child {
		border-style: dashed;
		border-width: 1.5px;
	}

	.node-icon {
		font-size: 16px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.node-label {
		flex: 1;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	:deep(.vue-flow__handle) {
		width: 8px;
		height: 8px;
		background-color: #409eff;
		border: 2px solid #ffffff;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
		border-radius: 50%;
		transition: background-color 0.2s;

		&:hover {
			background-color: #66b1ff;
		}
	}
}

.child-badge {
	position: absolute;
	top: -8px;
	right: -4px;
	font-size: 10px;
	padding: 1px 6px;
	background: rgba(230, 162, 60, 0.15);
	color: var(--el-color-warning);
	border-radius: 4px;
	white-space: nowrap;
}

.node-incomplete-dot {
	position: absolute;
	top: -3px;
	left: 18px;
	width: 8px;
	height: 8px;
	background: var(--el-color-danger);
	border-radius: 50%;
	border: 2px solid #fff;
}

.node-start {
	border-left: 4px solid var(--el-color-success);
	.node-icon { color: var(--el-color-success); }
}
.node-llm {
	border-left: 4px solid var(--el-color-primary);
	.node-icon { color: var(--el-color-primary); }
}
.node-tool, .node-tool_executor {
	border-left: 4px solid #8a2be2;
	.node-icon { color: #8a2be2; }
}
.node-condition {
	border-left: 4px solid var(--el-color-warning);
	.node-icon { color: var(--el-color-warning); }
}
.node-switch {
	border-left: 4px solid #e6a23c;
	.node-icon { color: #e6a23c; }
}
.node-human_input {
	border-left: 4px solid var(--el-color-info);
	.node-icon { color: var(--el-color-info); }
}
.node-intent_classifier {
	border-left: 4px solid #20b2aa;
	.node-icon { color: #20b2aa; }
}
.node-loop_controller {
	border-left: 4px solid #d2691e;
	.node-icon { color: #d2691e; }
}
.node-batch_processor {
	border-left: 4px solid #00ced1;
	.node-icon { color: #00ced1; }
}
.node-image_generator {
	border-left: 4px solid #ff69b4;
	.node-icon { color: #ff69b4; }
}
.node-end {
	border-left: 4px solid var(--el-color-danger);
	.node-icon { color: var(--el-color-danger); }
}

.custom-flow-node-wrapper {
	position: relative;
}

.node-run-log {
	position: absolute;
	top: 100%;
	left: 0;
	margin-top: 6px;
	width: 320px;
	background: #ffffff;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
	z-index: 1000;
	pointer-events: auto;
	display: flex;
	flex-direction: column;
	
	&.status-success { border-top: 3px solid var(--el-color-success); }
	&.status-error { border-top: 3px solid var(--el-color-danger); }
	&.status-running { border-top: 3px solid var(--el-color-primary); }
	
	.log-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 10px 12px;
		cursor: pointer;
		background: #fcfcfc;
		border-radius: 8px 8px 0 0;
		transition: background 0.2s;
		
		&:hover {
			background: var(--el-fill-color-light);
		}
		
		.log-status {
			display: flex;
			align-items: center;
			gap: 6px;
			font-size: 13px;
			font-weight: 600;
			color: var(--el-text-color-primary);
			
			.time-cost {
				font-size: 11px;
				color: var(--el-text-color-secondary);
				background: var(--el-fill-color-light);
				padding: 1px 6px;
				border-radius: 10px;
				margin-left: 4px;
			}
		}
		
		.expand-icon {
			font-size: 14px;
			color: var(--el-text-color-secondary);
		}
	}
	
	.log-body {
		padding: 12px;
		border-top: 1px solid var(--el-border-color-lighter);
		max-height: 280px;
		overflow-y: auto;
		
		/* 滚动条美化 */
		&::-webkit-scrollbar { width: 4px; height: 4px; }
		&::-webkit-scrollbar-thumb { background: #dcdfe6; border-radius: 2px; }
		&::-webkit-scrollbar-track { background: transparent; }
	}
	
	.log-section {
		margin-bottom: 12px;
		&:last-child { margin-bottom: 0; }
		
		.log-title {
			display: flex;
			align-items: center;
			gap: 6px;
			font-weight: 600;
			color: var(--el-text-color-regular);
			margin-bottom: 6px;
			font-size: 12px;
			
			.copy-btn {
				cursor: pointer;
				color: var(--el-text-color-secondary);
				transition: color 0.2s;
				&:hover {
					color: var(--el-color-primary);
				}
			}
		}
		
		.log-content {
			background: #f7f8fa;
			padding: 8px;
			border-radius: 6px;
			font-family: monospace;
			white-space: pre-wrap;
			word-break: break-all;
			color: var(--el-text-color-primary);
			font-size: 11px;
			line-height: 1.4;
			border: 1px solid var(--el-border-color-lighter);
		}
	}
	
	.log-empty {
		font-size: 12px;
		color: var(--el-text-color-placeholder);
		text-align: center;
		padding: 10px 0;
	}
}
</style>
