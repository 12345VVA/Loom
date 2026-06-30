<template>
	<div class="custom-flow-node-wrapper" :class="{ 'node-entering': isEntering }">
		<div
			class="custom-flow-node"
			:class="[meta.colorClass, { 'is-selected': selected, 'is-child': isChild }]"
			:style="nodeStyle"
		>
			<handle v-if="hasTarget" type="target" :position="Position.Left" />
			<el-icon class="node-icon">
				<component :is="meta.icon" />
			</el-icon>
			<span class="node-label">{{ label }}</span>
			<span v-if="isChild" class="child-badge">{{ groupLabel }}</span>
			<el-tooltip
				v-if="incomplete"
				effect="dark"
				:content="$t('节点存在未完成的必填配置')"
				placement="top"
			>
				<span class="node-incomplete-dot" />
			</el-tooltip>
			<div class="node-actions" v-if="canTestNode">
				<el-tooltip effect="dark" :content="$t('测试节点')" placement="top">
					<el-icon class="play-btn" @click.stop="handleTestNode"><video-play /></el-icon>
				</el-tooltip>
			</div>

			<!-- 默认单输出 Handle -->
			<handle
				v-if="hasSource && !customOutputHandles?.length"
				type="source"
				:position="Position.Right"
			/>

			<!-- 自定义多输出 Handle（condition / switch 等分支节点） -->
			<div v-if="customOutputHandles?.length" class="output-handles">
				<div v-for="h in customOutputHandles" :key="h.id" class="handle-group">
					<span
						class="handle-label"
						:class="h.labelClass"
						:style="{ top: h.topPercent + '%' }"
						>{{ h.label }}</span
					>
					<handle
						:id="h.id"
						type="source"
						:position="Position.Right"
						:style="{ top: h.topPercent + '%' }"
						class="custom-handle"
						:class="h.handleClass"
					/>
				</div>
			</div>
		</div>

		<!-- 节点下方的执行日志展示 -->
		<div v-if="runLog" class="node-run-log" :class="'status-' + runLog.status">
			<!-- 头部状态栏 -->
			<div class="log-header" @click="isLogExpanded = !isLogExpanded">
				<div class="log-status">
					<el-icon v-if="runLog.status === 'success'" color="#67c23a"
						><circle-check-filled
					/></el-icon>
					<el-icon v-else-if="runLog.status === 'error'" color="#f56c6c"
						><circle-close-filled
					/></el-icon>
					<el-icon
						v-else-if="runLog.status === 'running'"
						class="is-loading"
						color="#409eff"
						><loading
					/></el-icon>
					<el-icon v-else color="#909399"><info-filled /></el-icon>

					<span class="status-text" v-if="runLog">
						{{ statusText }}
					</span>
					<span v-if="runLog.timeCost" class="time-cost">{{ runLog.timeCost }}ms</span>
				</div>
				<el-icon class="expand-icon"
					><arrow-down v-if="isLogExpanded" /><arrow-right v-else
				/></el-icon>
			</div>

			<div v-show="isLogExpanded" class="log-body">
				<div v-if="runLog.inputData" class="log-section">
					<div class="log-title">
						<span>{{ $t('输入') }}</span>
						<el-icon
							class="copy-btn"
							@click.stop="copyToClipboard(formatJson(runLog.inputData))"
							><copy-document
						/></el-icon>
					</div>
					<div class="log-content" v-html="highlightJson(runLog.inputData)"></div>
				</div>
				<div v-if="runLog.outputData" class="log-section">
					<div class="log-title">
						<span>{{ $t('输出') }}</span>
						<el-icon
							class="copy-btn"
							@click.stop="copyToClipboard(formatJson(runLog.outputData))"
							><copy-document
						/></el-icon>
					</div>
					<div class="log-content" v-html="highlightJson(runLog.outputData)"></div>
				</div>
				<div v-if="!runLog.inputData && !runLog.outputData" class="log-empty">
					{{ $t('本次运行暂无数据') }}
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
defineOptions({ name: 'workflow-node-base' });
import { Handle, Position, useNode } from '@vue-flow/core';
import { computed, ref, onMounted, inject } from 'vue';
import {
	CircleCheckFilled,
	CircleCloseFilled,
	Loading,
	InfoFilled,
	ArrowDown,
	ArrowRight,
	CopyDocument,
	VideoPlay
} from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';
import { formatJson, copyToClipboard } from '../../utils';
import { getNodeMeta } from '../../utils/node-type-registry';
import { UNTESTABLE_NODE_TYPES, OPEN_NODE_TEST_DIALOG_KEY } from '../constants';
import type { CustomOutputHandle } from './types';

const { t } = useI18n();

interface Props {
	label: string;
	selected?: boolean;
	icon?: any;
	nodeClass?: string;
	hasTarget?: boolean;
	hasSource?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	incomplete?: boolean;
	nodeHeight?: number;
	customOutputHandles?: CustomOutputHandle[];
}

const props = withDefaults(defineProps<Props>(), {
	hasTarget: true,
	hasSource: true,
	nodeHeight: 42
});

const isEntering = ref(true);

onMounted(() => {
	setTimeout(() => {
		isEntering.value = false;
	}, 300);
});

const { node } = useNode();
const meta = computed(() => getNodeMeta(node.type));
const runLog = computed(() => node.data?.runLog);
const isLogExpanded = ref(true);

const openNodeTestDialog = inject(OPEN_NODE_TEST_DIALOG_KEY);

const canTestNode = computed(() => {
	return !UNTESTABLE_NODE_TYPES.includes(node.type);
});

function handleTestNode() {
	if (openNodeTestDialog) {
		openNodeTestDialog(node.id);
	}
}

const statusText = computed(() => {
	const s = runLog.value?.status;
	if (s === 'success') return t('运行成功');
	if (s === 'error') return t('运行失败');
	if (s === 'running') return t('试运行中...');
	return t('准备中');
});

const nodeStyle = computed(() => {
	if (props.customOutputHandles?.length) {
		return { height: props.nodeHeight + 'px' };
	}
	return {};
});

function highlightJson(data: any): string {
	const jsonStr = formatJson(data);
	if (!jsonStr) return '';
	let html = jsonStr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	html = html.replace(
		/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
		function (match) {
			let cls = 'json-number';
			if (/^"/.test(match)) {
				if (/:$/.test(match)) {
					cls = 'json-key';
				} else {
					cls = 'json-string';
				}
			} else if (/true|false/.test(match)) {
				cls = 'json-boolean';
			} else if (/null/.test(match)) {
				cls = 'json-null';
			}
			return '<span class="' + cls + '">' + match + '</span>';
		}
	);
	return html;
}
</script>

<style lang="scss" scoped>
@use '../workflow-shared.scss';

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
		box-shadow:
			0 0 0 2px rgba(64, 158, 255, 0.2),
			0 4px 12px rgba(64, 158, 255, 0.1);
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

	.node-actions {
		display: flex;
		align-items: center;
		margin-left: auto;
		padding-left: 6px;
	}

	.play-btn {
		cursor: pointer;
		color: var(--el-text-color-secondary);
		font-size: 16px;
		transition: all 0.2s;

		&:hover {
			color: var(--el-color-success);
			transform: scale(1.1);
		}
	}

	:deep(.vue-flow__handle) {
		width: 8px;
		height: 8px;
		background-color: #409eff;
		border: 2px solid #ffffff;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
		border-radius: 50%;
		transition:
			background-color 0.2s,
			transform 0.2s;

		&:hover {
			background-color: #66b1ff;
			transform: scale(1.3);
		}
	}
}

/* 自定义多输出 Handle 区域 */
.output-handles {
	position: absolute;
	right: 0;
	top: 0;
	bottom: 0;
	width: 12px;
}

.handle-group {
	display: flex;
	align-items: center;
}

.handle-label {
	position: absolute;
	right: 16px;
	font-size: 10px;
	font-weight: 700;
	transform: translateY(-50%);
	z-index: 2;
	user-select: none;

	&--true {
		color: #67c23a;
	}

	&--false {
		color: #f56c6c;
	}

	&--default {
		color: #909399;
		font-weight: 400;
	}

	&--case {
		color: #e6a23c;
		max-width: 60px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
}

.custom-handle {
	&.handle-true {
		:deep(.vue-flow__handle) {
			background-color: #67c23a !important;
		}
	}

	&.handle-false {
		:deep(.vue-flow__handle) {
			background-color: #f56c6c !important;
		}
	}

	&.handle-default {
		:deep(.vue-flow__handle) {
			background-color: #909399 !important;
		}
	}

	&.handle-case {
		:deep(.vue-flow__handle) {
			background-color: #e6a23c !important;
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
	border-left: 4px solid var(--wf-color-start);
	.node-icon {
		color: var(--wf-color-start);
	}
}
.node-llm {
	border-left: 4px solid var(--wf-color-llm);
	.node-icon {
		color: var(--wf-color-llm);
	}
}
.node-tool,
.node-tool_executor {
	border-left: 4px solid var(--wf-color-tool);
	.node-icon {
		color: var(--wf-color-tool);
	}
}
.node-condition {
	border-left: 4px solid var(--wf-color-condition);
	.node-icon {
		color: var(--wf-color-condition);
	}
}
.node-switch {
	border-left: 4px solid var(--wf-color-switch);
	.node-icon {
		color: var(--wf-color-switch);
	}
}
.node-human_input {
	border-left: 4px solid var(--wf-color-human-input);
	.node-icon {
		color: var(--wf-color-human-input);
	}
}
.node-intent_classifier {
	border-left: 4px solid var(--wf-color-intent-classifier);
	.node-icon {
		color: var(--wf-color-intent-classifier);
	}
}
.node-loop_controller {
	border-left: 4px solid var(--wf-color-loop-controller);
	.node-icon {
		color: var(--wf-color-loop-controller);
	}
}
.node-batch_processor {
	border-left: 4px solid var(--wf-color-batch-processor);
	.node-icon {
		color: var(--wf-color-batch-processor);
	}
}
.node-image_generator {
	border-left: 4px solid var(--wf-color-image-generator);
	.node-icon {
		color: var(--wf-color-image-generator);
	}
}
.node-end {
	border-left: 4px solid var(--wf-color-end);
	.node-icon {
		color: var(--wf-color-end);
	}
}
.node-variable_assignment {
	border-left: 4px solid var(--wf-color-variable-assignment);
	.node-icon {
		color: var(--wf-color-variable-assignment);
	}
}
.node-variable_transform {
	border-left: 4px solid var(--wf-color-variable-transform);
	.node-icon {
		color: var(--wf-color-variable-transform);
	}
}

/*
 * ⚠️ 节点动画防坑说明 ⚠️
 * 节点相关的入场/缩放动画必须加在 `.custom-flow-node-wrapper` 这个内部容器上，
 * 而绝不能加在 Vue Flow 的外部容器 `.vue-flow__node` 上。
 * 因为外层容器的坐标是通过内联的 `transform: translate(x, y)` 计算渲染的，
 * 如果 CSS animation 携带了 `transform: scale`，会把内联的位移覆盖为0，导致所有节点塌陷重叠！
 */
.custom-flow-node-wrapper {
	position: relative;
	&.node-entering {
		animation: wf-pop-in 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
	}
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

	&.status-success {
		border-top: 3px solid var(--el-color-success);
	}
	&.status-error {
		border-top: 3px solid var(--el-color-danger);
	}
	&.status-running {
		border-top: 3px solid var(--el-color-primary);
	}

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
		&::-webkit-scrollbar {
			width: 4px;
			height: 4px;
		}
		&::-webkit-scrollbar-thumb {
			background: #dcdfe6;
			border-radius: 2px;
		}
		&::-webkit-scrollbar-track {
			background: transparent;
		}
	}

	.log-section {
		margin-bottom: 12px;
		&:last-child {
			margin-bottom: 0;
		}

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

			:deep(.json-string) {
				color: #067b14;
			}
			:deep(.json-number) {
				color: #098658;
			}
			:deep(.json-boolean) {
				color: #0000ff;
			}
			:deep(.json-null) {
				color: #0000ff;
			}
			:deep(.json-key) {
				color: #a31515;
				font-weight: bold;
			}
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
