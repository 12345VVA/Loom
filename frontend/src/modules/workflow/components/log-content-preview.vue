<template>
	<div class="log-content-preview">
		<!-- 1. 文案展示模式 (如果包含 copy_text) -->
		<div v-if="extractedCopyText" class="section-card">
			<div class="card-header">
				<div class="title-wrap">
					<el-tag size="small" type="primary" effect="dark">{{
						$t('小红书 / 正文文案')
					}}</el-tag>
					<span class="char-count">{{ extractedCopyText.length }} {{ $t('字') }}</span>
				</div>
				<el-button size="small" type="primary" link @click="copyText(extractedCopyText)">
					<template #icon>
						<workflow-icon name="copy" :size="13" />
					</template>
					{{ $t('复制文案') }}
				</el-button>
			</div>
			<div class="copy-text-body">
				<div class="formatted-text">{{ extractedCopyText }}</div>
			</div>
		</div>

		<!-- 2. 故事段落卡片列表 (如果包含 paragraphs) -->
		<div v-if="extractedParagraphs.length > 0" class="section-card" style="margin-top: 12px">
			<div class="card-header">
				<div class="title-wrap">
					<el-tag size="small" type="success" effect="dark">{{
						$t('故事段落与绘图提示词')
					}}</el-tag>
					<span class="char-count"
						>{{ $t('共') }} {{ extractedParagraphs.length }} {{ $t('段') }}</span
					>
				</div>
			</div>
			<div class="paragraphs-list">
				<div v-for="(p, idx) in extractedParagraphs" :key="idx" class="paragraph-item">
					<div class="p-index">
						<span class="badge">#{{ p.paragraph_id || idx + 1 }}</span>
					</div>
					<div class="p-content">
						<div v-if="p.story_text" class="story-text">
							{{ p.story_text }}
						</div>
						<div v-if="p.scene_prompt" class="scene-prompt">
							<div class="prompt-header">
								<span class="prompt-label">{{ $t('画图提示词 (Prompt)：') }}</span>
								<el-button size="small" link @click="copyText(p.scene_prompt)">
									<template #icon>
										<workflow-icon name="copy" :size="13" />
									</template>
									{{ $t('复制') }}
								</el-button>
							</div>
							<div class="prompt-body">{{ p.scene_prompt }}</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 3. 策划规划信息 (如果包含 plan_output 或 category/book_title) -->
		<div v-if="extractedPlan" class="section-card" style="margin-top: 12px">
			<div class="card-header">
				<el-tag size="small" type="warning" effect="dark">{{ $t('选题策划信息') }}</el-tag>
			</div>
			<el-descriptions :column="1" border size="small" class="plan-descriptions">
				<el-descriptions-item v-if="extractedPlan.book_title" :label="$t('绘本书名')">
					<strong>{{ extractedPlan.book_title }}</strong>
				</el-descriptions-item>
				<el-descriptions-item v-if="extractedPlan.note_title" :label="$t('笔记标题')">
					{{ extractedPlan.note_title }}
				</el-descriptions-item>
				<el-descriptions-item v-if="extractedPlan.category" :label="$t('分类')">
					<el-tag size="small" effect="plain">{{ extractedPlan.category }}</el-tag>
				</el-descriptions-item>
				<el-descriptions-item v-if="extractedPlan.pain_point" :label="$t('痛点分析')">
					{{ extractedPlan.pain_point }}
				</el-descriptions-item>
				<el-descriptions-item
					v-if="extractedPlan.core_points?.length"
					:label="$t('核心要点')"
				>
					<ul class="points-list">
						<li v-for="(pt, i) in extractedPlan.core_points" :key="i">{{ pt }}</li>
					</ul>
				</el-descriptions-item>
				<el-descriptions-item v-if="extractedPlan.tags?.length" :label="$t('标签')">
					<div class="tags-wrap">
						<el-tag
							v-for="tag in extractedPlan.tags"
							:key="tag"
							size="small"
							type="info"
						>
							#{{ tag }}
						</el-tag>
					</div>
				</el-descriptions-item>
			</el-descriptions>
		</div>

		<!-- 4. 常规键值概览 (当没有上述特定业务字段时，展示普通结构体顶层字段) -->
		<div v-if="!hasSpecialContent && generalFields.length > 0" class="section-card">
			<div class="card-header">
				<el-tag size="small" type="info" effect="plain">{{ $t('数据字段概览') }}</el-tag>
			</div>
			<el-descriptions :column="1" border size="small">
				<el-descriptions-item v-for="f in generalFields" :key="f.key" :label="f.key">
					<span class="field-val">{{ f.val }}</span>
				</el-descriptions-item>
			</el-descriptions>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import WorkflowIcon from './workflow-icon.vue';
import { copyToClipboard } from '../utils';
import { useI18n } from 'vue-i18n';

defineOptions({ name: 'workflow-log-content-preview' });

const props = defineProps<{
	data?: any;
}>();

const { t } = useI18n();

const parsedObj = computed<any>(() => {
	if (!props.data) return null;
	if (typeof props.data === 'object') return props.data;
	try {
		return JSON.parse(props.data);
	} catch {
		return null;
	}
});

// 递归查找特定字段值
function findDeepValue(obj: any, targetKey: string): any {
	if (!obj || typeof obj !== 'object') return undefined;
	if (targetKey in obj) return obj[targetKey];
	for (const k of Object.keys(obj)) {
		if (typeof obj[k] === 'object') {
			const res = findDeepValue(obj[k], targetKey);
			if (res !== undefined) return res;
		}
	}
	return undefined;
}

// 提取文案
const extractedCopyText = computed<string>(() => {
	if (!parsedObj.value) return '';
	return findDeepValue(parsedObj.value, 'copy_text') || '';
});

// 提取段落
const extractedParagraphs = computed<any[]>(() => {
	if (!parsedObj.value) return [];
	const p =
		findDeepValue(parsedObj.value, 'paragraphs') ||
		findDeepValue(parsedObj.value, 'paragraphs_array');
	return Array.isArray(p) ? p : [];
});

// 提取策划
const extractedPlan = computed<any>(() => {
	if (!parsedObj.value) return null;
	const plan =
		findDeepValue(parsedObj.value, 'plan_output')?.output ||
		findDeepValue(parsedObj.value, 'plan_output') ||
		null;
	if (plan && (plan.book_title || plan.category || plan.pain_point)) {
		return plan;
	}
	if (parsedObj.value.book_title || parsedObj.value.pain_point) {
		return parsedObj.value;
	}
	return null;
});

const hasSpecialContent = computed(() => {
	return (
		!!extractedCopyText.value || extractedParagraphs.value.length > 0 || !!extractedPlan.value
	);
});

// 普通顶层键值字段
const generalFields = computed(() => {
	if (!parsedObj.value || typeof parsedObj.value !== 'object') return [];
	return Object.entries(parsedObj.value).map(([key, val]) => {
		let displayVal = '';
		if (typeof val === 'object') {
			displayVal = JSON.stringify(val);
			if (displayVal.length > 120) displayVal = displayVal.substring(0, 120) + '...';
		} else {
			displayVal = String(val);
		}
		return { key, val: displayVal };
	});
});

function copyText(str: string) {
	copyToClipboard(str, t('复制成功'), t('复制失败'));
}
</script>

<style lang="scss" scoped>
.log-content-preview {
	.section-card {
		border: 1px solid var(--el-border-color-lighter);
		border-radius: 8px;
		background: var(--el-bg-color-overlay);
		overflow: hidden;

		.card-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 8px 12px;
			background: var(--el-fill-color-light);
			border-bottom: 1px solid var(--el-border-color-lighter);

			.title-wrap {
				display: flex;
				align-items: center;
				gap: 8px;

				.char-count {
					font-size: 11px;
					color: var(--el-text-color-secondary);
				}
			}
		}
	}

	.copy-text-body {
		padding: 12px;
		max-height: 360px;
		overflow-y: auto;

		.formatted-text {
			font-size: 13px;
			line-height: 1.8;
			white-space: pre-wrap;
			word-break: break-all;
			color: var(--el-text-color-primary);
		}
	}

	.paragraphs-list {
		padding: 10px;
		max-height: 380px;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 10px;

		.paragraph-item {
			display: flex;
			gap: 10px;
			padding: 10px;
			background: var(--el-fill-color-blank);
			border: 1px solid var(--el-border-color-extra-light);
			border-radius: 6px;

			.p-index {
				.badge {
					display: inline-block;
					padding: 2px 6px;
					border-radius: 4px;
					background: var(--el-color-primary-light-9);
					color: var(--el-color-primary);
					font-size: 11px;
					font-weight: bold;
					font-family: monospace;
				}
			}

			.p-content {
				flex: 1;
				min-width: 0;

				.story-text {
					font-size: 13px;
					line-height: 1.6;
					color: var(--el-text-color-primary);
					margin-bottom: 8px;
				}

				.scene-prompt {
					padding: 8px 10px;
					background: var(--el-fill-color-light);
					border-radius: 4px;
					font-size: 11px;

					.prompt-header {
						display: flex;
						justify-content: space-between;
						align-items: center;
						margin-bottom: 4px;

						.prompt-label {
							color: var(--el-text-color-secondary);
							font-weight: 500;
						}
					}

					.prompt-body {
						color: var(--el-text-color-regular);
						font-family: ui-monospace, SFMono-Regular, monospace;
						word-break: break-all;
						line-height: 1.5;
					}
				}
			}
		}
	}

	.plan-descriptions {
		padding: 10px;

		.points-list {
			margin: 0;
			padding-left: 18px;
			line-height: 1.6;
			font-size: 12px;
		}

		.tags-wrap {
			display: flex;
			flex-wrap: wrap;
			gap: 6px;
		}
	}

	.field-val {
		font-family: monospace;
		font-size: 12px;
		word-break: break-all;
	}
}
</style>
