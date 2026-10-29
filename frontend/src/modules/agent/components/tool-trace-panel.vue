<template>
	<div class="tool-trace-panel">
		<div v-if="!blocks.length" class="empty">{{ t('agent.toolTrace.empty') }}</div>
		<el-timeline v-else>
			<el-timeline-item
				v-for="(block, index) in blocks"
				:key="block.toolCallId || index"
				:type="timelineType(block.status)"
				:timestamp="block.timestamp ? formatDateTime(block.timestamp) : undefined"
			>
				<div
					class="trace-line"
					:class="{ 'is-clickable': hasDetail(block) }"
					@click="toggleExpand(block)"
				>
					<el-icon v-if="hasDetail(block)" class="expand-icon" :class="{ 'is-rotated': isExpanded(block) }">
						<arrow-right />
					</el-icon>
					<span class="tool-name">{{ block.toolName }}</span>
					<el-tag size="small" :type="tagType(block.status)">{{ statusText(block.status) }}</el-tag>
					<el-tag
						v-if="block.skippedReason && block.skippedReason !== 'error'"
						size="small"
						type="warning"
						effect="plain"
					>
						{{ reasonText(block.skippedReason) }}
					</el-tag>
					<!-- E3：写操作目标引用（"asset:3"）——审计可追溯；只读工具恒空 -->
					<el-tag v-if="block.targetRef" size="small" type="info" effect="plain">{{ block.targetRef }}</el-tag>
					<span v-if="block.duration != null" class="duration">{{ humanizeDuration(block.duration) }}</span>
				</div>
				<!-- 参数/结果摘要可展开（此前只藏 hover tooltip，不可发现） -->
				<el-collapse-transition>
					<div v-if="isExpanded(block)" class="detail-body">
						<div v-if="block.argsSummary" class="detail-row">
							<span class="detail-label">{{ t('agent.toolTrace.args') }}</span>
							<pre class="detail-content">{{ block.argsSummary }}</pre>
						</div>
						<div v-if="block.resultSummary" class="detail-row">
							<span class="detail-label">{{ t('agent.toolTrace.result') }}</span>
							<pre class="detail-content">{{ block.resultSummary }}</pre>
						</div>
					</div>
				</el-collapse-transition>
				<div v-if="block.error" class="error-line">{{ block.error }}</div>
			</el-timeline-item>
		</el-timeline>
	</div>
</template>

<script lang="ts" setup name="agent-tool-trace-panel">
import { computed, reactive } from 'vue';
import { useI18n } from 'vue-i18n';
import { ArrowRight } from '@element-plus/icons-vue';
import { formatDateTime, humanizeDuration } from '../utils/trace-format';

export interface TraceBlock {
	toolCallId?: string;
	toolName: string;
	status: 'running' | 'done' | 'skipped' | 'failed';
	duration?: number;
	timestamp?: string;
	/** 审计增强（调用追踪 A3/P3）：拒绝原因结构化列 + 参数/结果摘要 + 错误文本 */
	skippedReason?: string;
	/** E3 写操作目标引用（"asset:3" / "media:7"） */
	targetRef?: string;
	argsSummary?: string;
	resultSummary?: string;
	error?: string;
}

const props = defineProps<{
	/** 会话 messages（tool 角色行）或调试台事件块 */
	logs: TraceBlock[];
}>();

const { t } = useI18n();

const blocks = computed(() => props.logs || []);

/** 展开态（reactive Set 保响应；key 用 toolCallId） */
const expandedIds = reactive(new Set<string>());

function expandKey(block: TraceBlock) {
	return block.toolCallId || block.toolName;
}

function hasDetail(block: TraceBlock) {
	return Boolean(block.argsSummary || block.resultSummary);
}

function isExpanded(block: TraceBlock) {
	return expandedIds.has(expandKey(block));
}

function toggleExpand(block: TraceBlock) {
	const key = expandKey(block);
	if (expandedIds.has(key)) {
		expandedIds.delete(key);
	} else {
		expandedIds.add(key);
	}
}

function timelineType(status: TraceBlock['status']) {
	if (status === 'done') return 'success';
	if (status === 'failed') return 'danger';
	if (status === 'skipped') return 'warning';
	return 'primary';
}

function tagType(status: TraceBlock['status']) {
	if (status === 'done') return 'success';
	if (status === 'failed') return 'danger';
	if (status === 'skipped') return 'warning';
	return 'primary';
}

function statusText(status: TraceBlock['status']) {
	const map: Record<string, string> = {
		running: t('agent.toolTrace.running'),
		done: t('agent.toolTrace.done'),
		skipped: t('agent.toolTrace.skipped'),
		failed: t('agent.toolTrace.failed')
	};
	return map[status] || status;
}

function reasonText(reason: string) {
	const map: Record<string, string> = {
		cancelled: t('agent.toolTrace.reasonCancelled'),
		soft_failure: t('agent.toolTrace.reasonSoftFailure'),
		invalid_args: t('agent.toolTrace.reasonInvalidArgs'),
		denied: t('agent.toolTrace.reasonDenied'),
		not_bound: t('agent.toolTrace.reasonNotBound'),
		contract_incompatible: t('agent.toolTrace.reasonContract'),
		budget_exhausted: t('agent.toolTrace.reasonBudget'),
		error: t('agent.toolTrace.reasonError')
	};
	return map[reason] || reason;
}
</script>

<style lang="scss" scoped>
.tool-trace-panel {
	padding: 4px 0;

	.empty {
		color: var(--el-text-color-secondary);
		font-size: 13px;
		text-align: center;
		padding: 12px 0;
	}

	.trace-line {
		display: flex;
		align-items: center;
		gap: 8px;

		&.is-clickable {
			cursor: pointer;
			user-select: none;
		}

		.expand-icon {
			font-size: 12px;
			color: var(--el-text-color-secondary);
			transition: transform 0.2s;

			&.is-rotated {
				transform: rotate(90deg);
			}
		}

		.tool-name {
			font-weight: 500;
			cursor: default;
		}

		.duration {
			color: var(--el-text-color-secondary);
			font-size: 12px;
		}
	}

	.detail-body {
		margin-top: 6px;
		padding: 8px 10px;
		border-radius: 6px;
		background: var(--el-fill-color-lighter);
		display: flex;
		flex-direction: column;
		gap: 6px;

		.detail-row {
			display: flex;
			gap: 8px;
			font-size: 12px;

			.detail-label {
				flex-shrink: 0;
				color: var(--el-text-color-secondary);
				line-height: 20px;
			}

			.detail-content {
				margin: 0;
				flex: 1;
				white-space: pre-wrap;
				word-break: break-all;
				font-family: var(--el-font-family, monospace);
				line-height: 20px;
			}
		}
	}

	.error-line {
		margin-top: 4px;
		font-size: 12px;
		color: var(--el-color-danger);
		word-break: break-all;
	}
}
</style>
