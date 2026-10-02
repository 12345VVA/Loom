<template>
	<div class="ai-payload-inspector">
		<el-collapse v-model="activeNames">
			<el-collapse-item name="debug">
				<template #title>
					<div class="inspector-title">
						<el-icon><info-filled /></el-icon>
						<span>{{ title || $t('请求与响应数据报文') }}</span>
						<el-tag v-if="result?.requestId" size="small" type="info" class="ml-2">
							ID: {{ result.requestId }}
						</el-tag>
					</div>
				</template>

				<!-- 元数据属性 Badge 列表 -->
				<div v-if="result" class="inspector-meta-grid">
					<div class="meta-item">
						<span class="meta-k">Provider</span>
						<span class="meta-v">{{ result.provider || '-' }}</span>
					</div>
					<div class="meta-item">
						<span class="meta-k">Model</span>
						<span class="meta-v">{{ result.model || '-' }}</span>
					</div>
					<div class="meta-item">
						<span class="meta-k">Profile</span>
						<span class="meta-v">{{ result.profile || '-' }}</span>
					</div>
					<div class="meta-item">
						<span class="meta-k">Request / Task ID</span>
						<span class="meta-v">{{ result.requestId || result.taskId || '-' }}</span>
					</div>
				</div>

				<!-- 报文原始 JSON Tabs -->
				<el-tabs class="raw-tabs">
					<el-tab-pane :label="$t('请求报文')">
						<div class="json-box">
							<el-button
								v-if="lastPayload"
								size="small"
								class="json-copy-btn"
								@click="copyJson(lastPayload)"
							>
								{{ $t('复制 JSON') }}
							</el-button>
							<pre>{{ formatJson(lastPayload) }}</pre>
						</div>
					</el-tab-pane>
					<el-tab-pane :label="$t('响应数据')">
						<div class="json-box">
							<el-button
								v-if="result"
								size="small"
								class="json-copy-btn"
								@click="copyJson(result)"
							>
								{{ $t('复制 JSON') }}
							</el-button>
							<pre>{{ formatJson(result) }}</pre>
						</div>
					</el-tab-pane>
				</el-tabs>
			</el-collapse-item>
		</el-collapse>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-payload-inspector'
});

import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { InfoFilled } from '@element-plus/icons-vue';

const { t } = useI18n();

const props = withDefaults(
	defineProps<{
		result?: any;
		lastPayload?: any;
		title?: string;
		defaultOpen?: boolean;
	}>(),
	{
		result: null,
		lastPayload: null,
		title: '',
		defaultOpen: false
	}
);

const activeNames = ref<string[]>(props.defaultOpen ? ['debug'] : []);

function formatJson(val: any): string {
	if (!val) return '{\n  // 无数据\n}';
	try {
		return JSON.stringify(val, null, 2);
	} catch (e) {
		return String(val);
	}
}

async function copyJson(data: any) {
	try {
		const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
		await navigator.clipboard.writeText(text);
		ElMessage.success(t('报文 JSON 已复制到剪贴板'));
	} catch (e) {
		ElMessage.warning(t('复制失败，请手动选择复制'));
	}
}
</script>

<style lang="scss" scoped>
.ai-payload-inspector {
	background: var(--el-bg-color);
	border-top: 1px solid var(--el-border-color-lighter);

	:deep(.el-collapse) {
		border-top: none;
		border-bottom: none;

		.el-collapse-item__header {
			background: var(--el-fill-color-light);
			padding: 0 16px;
			height: 40px;
			line-height: 40px;
			font-size: 13px;
			border-bottom: 1px solid var(--el-border-color-lighter);
		}

		.el-collapse-item__content {
			padding: 12px 16px;
			background: var(--el-bg-color);
		}
	}

	.inspector-title {
		display: flex;
		align-items: center;
		gap: 6px;
		font-weight: 500;
		color: var(--el-text-color-regular);

		.el-icon {
			font-size: 15px;
			color: var(--el-color-info);
		}
	}

	.inspector-meta-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 8px;
		margin-bottom: 12px;
		padding: 10px;
		background: var(--el-fill-color-extra-light);
		border-radius: 6px;

		.meta-item {
			display: flex;
			align-items: center;
			gap: 6px;
			font-size: 12px;

			.meta-k {
				color: var(--el-text-color-secondary);
				font-weight: 500;
			}
			.meta-v {
				color: var(--el-text-color-primary);
				font-family: monospace;
				overflow: hidden;
				text-overflow: ellipsis;
				white-space: nowrap;
			}
		}
	}

	.raw-tabs {
		:deep(.el-tabs__header) {
			margin: 0 0 8px 0;
		}

		.json-box {
			position: relative;
			background: var(--el-fill-color-darker);
			border-radius: 6px;
			padding: 10px;
			max-height: 240px;
			overflow: auto;

			.json-copy-btn {
				position: absolute;
				top: 8px;
				right: 8px;
				z-index: 2;
				opacity: 0.85;

				&:hover {
					opacity: 1;
				}
			}

			pre {
				margin: 0;
				font-family: 'Fira Code', Menlo, Consolas, monospace;
				font-size: 12px;
				line-height: 1.5;
				color: #e6edf3;
				white-space: pre-wrap;
				word-break: break-all;
			}
		}
	}
}
</style>
