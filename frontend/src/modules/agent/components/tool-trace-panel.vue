<template>
	<div class="tool-trace-panel">
		<div v-if="!blocks.length" class="empty">{{ t('agent.toolTrace.empty') }}</div>
		<el-timeline v-else>
			<el-timeline-item
				v-for="(block, index) in blocks"
				:key="block.toolCallId || index"
				:type="timelineType(block.status)"
				:timestamp="block.timestamp"
			>
				<div class="trace-line">
					<el-tooltip v-if="block.argsSummary || block.resultSummary" placement="top" effect="dark">
						<template #content>
							<div class="tip-content">
								<div v-if="block.argsSummary" class="tip-line">
									{{ t('agent.toolTrace.args') }}: {{ block.argsSummary }}
								</div>
								<div v-if="block.resultSummary" class="tip-line">
									{{ t('agent.toolTrace.result') }}: {{ block.resultSummary }}
								</div>
							</div>
						</template>
						<span class="tool-name">{{ block.toolName }}</span>
					</el-tooltip>
					<span v-else class="tool-name">{{ block.toolName }}</span>
					<el-tag size="small" :type="tagType(block.status)">{{ statusText(block.status) }}</el-tag>
					<el-tag
						v-if="block.skippedReason && block.skippedReason !== 'error'"
						size="small"
						type="warning"
						effect="plain"
					>
						{{ reasonText(block.skippedReason) }}
					</el-tag>
					<span v-if="block.duration" class="duration">{{ block.duration }}ms</span>
				</div>
				<div v-if="block.error" class="error-line">{{ block.error }}</div>
			</el-timeline-item>
		</el-timeline>
	</div>
</template>

<script lang="ts" setup name="agent-tool-trace-panel">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

export interface TraceBlock {
	toolCallId?: string;
	toolName: string;
	status: 'running' | 'done' | 'skipped' | 'failed';
	duration?: number;
	timestamp?: string;
	/** 审计增强（调用追踪 A3/P3）：拒绝原因结构化列 + 参数/结果摘要 + 错误文本 */
	skippedReason?: string;
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

		.tool-name {
			font-weight: 500;
			cursor: default;
		}

		.duration {
			color: var(--el-text-color-secondary);
			font-size: 12px;
		}
	}

	.error-line {
		margin-top: 4px;
		font-size: 12px;
		color: var(--el-color-danger);
		word-break: break-all;
	}
}

.tip-content {
	max-width: 360px;
	word-break: break-all;

	.tip-line {
		line-height: 18px;
	}
}
</style>
