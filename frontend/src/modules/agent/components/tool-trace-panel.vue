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
					<span class="tool-name">{{ block.toolName }}</span>
					<el-tag size="small" :type="tagType(block.status)">{{ statusText(block.status) }}</el-tag>
					<span v-if="block.duration" class="duration">{{ block.duration }}ms</span>
				</div>
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
		}

		.duration {
			color: var(--el-text-color-secondary);
			font-size: 12px;
		}
	}
}
</style>
