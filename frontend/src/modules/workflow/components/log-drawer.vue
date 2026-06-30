<template>
	<!--
		工作流执行日志抽屉（#25 抽取）：editor 测试运行日志与 instance 步骤执行日志共用。
		单项展开状态直接改 items 元素的 isExpanded（与抽取前行为一致：父级持有 reactive 引用）。
	-->
	<el-drawer
		:model-value="visible"
		:size="size"
		:title="title"
		destroy-on-close
		@update:model-value="(v: boolean) => emit('update:visible', v)"
		@close="emit('close')"
	>
		<div v-loading="loading" style="padding: 10px">
			<div
				v-if="status !== undefined || items.length > 0"
				class="log-drawer__toolbar"
			>
				<el-tag v-if="status !== undefined" :type="statusTagType">
					{{ $t('状态：') }}{{ status || $t('准备中') }}
				</el-tag>
				<div v-if="items.length > 0">
					<el-button size="small" @click="emit('expand-all')">{{ $t('展开全部') }}</el-button>
					<el-button size="small" @click="emit('collapse-all')">{{ $t('折叠全部') }}</el-button>
				</div>
			</div>

			<el-timeline v-if="items.length > 0">
				<el-timeline-item
					v-for="(item, index) in items"
					:key="index"
					:timestamp="formatTime(item.createTime)"
					:type="item.status === 'success' ? 'success' : 'danger'"
				>
					<el-card shadow="hover" style="margin-bottom: 10px">
						<template #header>
							<div class="log-drawer__card-header" @click="item.isExpanded = !item.isExpanded">
								<div style="display: flex; align-items: center; gap: 8px">
									<el-icon>
										<arrow-down v-if="item.isExpanded" />
										<arrow-right v-else />
									</el-icon>
									<strong style="font-size: 15px">{{ item.nodeName }}</strong>
								</div>
								<el-tag size="small" type="info">{{ item.nodeType }}</el-tag>
							</div>
						</template>
						<div class="log-payload" v-show="item.isExpanded">
							<div class="log-payload__section">
								<div class="section-header">
									<strong>{{ $t('上游输入：') }}</strong>
									<el-button
										link
										type="primary"
										:icon="CopyDocument"
										@click="copyToClipboard(formatJson(item.inputData))"
										>{{ $t('复制') }}</el-button
									>
								</div>
								<pre>{{ formatJson(item.inputData) }}</pre>
							</div>
							<div class="log-payload__section" style="margin-top: 10px">
								<div class="section-header">
									<strong>{{ $t('执行输出：') }}</strong>
									<el-button
										link
										type="primary"
										:icon="CopyDocument"
										@click="copyToClipboard(formatJson(item.outputData))"
										>{{ $t('复制') }}</el-button
									>
								</div>
								<pre>{{ formatJson(item.outputData) }}</pre>
							</div>
						</div>
					</el-card>
				</el-timeline-item>
			</el-timeline>
			<el-empty v-else :description="emptyText" />
		</div>
	</el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { ArrowDown, ArrowRight, CopyDocument } from '@element-plus/icons-vue';
import { formatJson, copyToClipboard, type WorkflowLogItem } from '../utils';
import dayjs from 'dayjs';

defineOptions({ name: 'workflow-log-drawer' });

const props = withDefaults(
	defineProps<{
		visible: boolean;
		items: WorkflowLogItem[];
		title?: string;
		size?: string;
		loading?: boolean;
		emptyText?: string;
		/** 提供则显示顶部状态 tag（editor 测试运行用） */
		status?: string;
		/** 时间格式：editor 测试日志用 HH:mm:ss，instance 步骤日志用完整日期 */
		timeFormat?: string;
	}>(),
	{
		title: '',
		size: '500px',
		loading: false,
		emptyText: '',
		timeFormat: 'HH:mm:ss'
	}
);

const emit = defineEmits<{
	(e: 'update:visible', v: boolean): void;
	(e: 'close'): void;
	(e: 'expand-all'): void;
	(e: 'collapse-all'): void;
}>();

const statusTagType = computed<'success' | 'danger' | 'primary'>(() => {
	if (props.status === 'success') return 'success';
	if (props.status === 'failed') return 'danger';
	return 'primary';
});

function formatTime(value?: string): string {
	return value ? dayjs(value).format(props.timeFormat) : '-';
}
</script>

<style lang="scss" scoped>
.log-drawer__toolbar {
	margin-bottom: 15px;
	display: flex;
	justify-content: space-between;
	align-items: center;
}

.log-drawer__card-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	cursor: pointer;
}

.log-payload {
	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 4px;
	}
	pre {
		background-color: var(--el-fill-color-light);
		padding: 10px;
		border-radius: 4px;
		font-family: monospace;
		font-size: 12px;
		margin: 4px 0 0 0;
		overflow-x: auto;
		white-space: pre-wrap;
		word-break: break-all;
	}
}
</style>
