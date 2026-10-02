<template>
	<div class="log-json-viewer" :class="{ 'is-empty': !hasContent }">
		<div v-if="showHeader" class="log-json-viewer__header">
			<div class="header-left">
				<el-tag v-if="title" size="small" type="info" effect="plain" class="title-tag">
					{{ title }}
				</el-tag>
				<span class="meta-stat" v-if="hasContent">
					{{ formatSize(rawString.length) }} · {{ lineCount }} {{ $t('行') }}
				</span>
			</div>
			<div class="header-actions">
				<el-input
					v-if="hasContent && searchable"
					v-model="searchKey"
					size="small"
					placeholder="Ctrl+F 搜索..."
					clearable
					class="search-input"
				>
					<template #prefix>
						<workflow-icon name="search" :size="13" />
					</template>
				</el-input>
				<el-tooltip :content="isFormatted ? $t('压缩单行') : $t('格式化')" placement="top">
					<el-button size="small" text @click="isFormatted = !isFormatted">
						<workflow-icon name="format" :size="14" />
					</el-button>
				</el-tooltip>
				<el-tooltip :content="$t('复制 JSON')" placement="top">
					<el-button size="small" text type="primary" @click="handleCopy">
						<template #icon>
							<workflow-icon name="copy" :size="13" />
						</template>
						{{ $t('复制') }}
					</el-button>
				</el-tooltip>
				<el-tooltip :content="$t('全屏查看')" placement="top">
					<el-button size="small" text @click="dialogVisible = true">
						<workflow-icon name="fullscreen" :size="14" />
					</el-button>
				</el-tooltip>
			</div>
		</div>

		<div
			class="log-json-viewer__body"
			:style="{ maxHeight: typeof maxHeight === 'number' ? `${maxHeight}px` : maxHeight }"
		>
			<template v-if="hasContent">
				<div class="code-container">
					<!-- 行号列 -->
					<div class="line-numbers" aria-hidden="true">
						<span v-for="n in lineCount" :key="n">{{ n }}</span>
					</div>
					<!-- 代码高亮内容 -->
					<div class="code-content">
						<pre class="highlight-code" v-html="highlightedHtml"></pre>
					</div>
				</div>
			</template>
			<div v-else class="empty-placeholder">
				<span class="empty-text">{{ emptyText || $t('无数据') }}</span>
			</div>
		</div>

		<!-- 放大全屏弹窗 -->
		<el-dialog
			v-model="dialogVisible"
			:title="title || $t('执行数据详情')"
			width="80vw"
			top="5vh"
			destroy-on-close
			append-to-body
			class="log-json-viewer__dialog"
		>
			<div class="dialog-toolbar">
				<span class="meta-stat">
					{{ formatSize(rawString.length) }} · {{ lineCount }} {{ $t('行') }}
				</span>
				<div style="display: flex; gap: 8px">
					<el-input
						v-model="searchKey"
						size="small"
						placeholder="搜索关键词..."
						clearable
						style="width: 220px"
					>
						<template #prefix>
							<workflow-icon name="search" :size="13" />
						</template>
					</el-input>
					<el-button size="small" type="primary" @click="handleCopy">
						<template #icon>
							<workflow-icon name="copy" :size="13" />
						</template>
						{{ $t('复制全部') }}
					</el-button>
				</div>
			</div>
			<div class="dialog-code-container">
				<div class="line-numbers" aria-hidden="true">
					<span v-for="n in lineCount" :key="n">{{ n }}</span>
				</div>
				<div class="code-content">
					<pre class="highlight-code" v-html="highlightedHtml"></pre>
				</div>
			</div>
		</el-dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import WorkflowIcon from './workflow-icon.vue';
import { copyToClipboard } from '../utils';
import { useI18n } from 'vue-i18n';

defineOptions({ name: 'workflow-log-json-viewer' });

const props = withDefaults(
	defineProps<{
		value?: any;
		title?: string;
		maxHeight?: string | number;
		showHeader?: boolean;
		searchable?: boolean;
		emptyText?: string;
	}>(),
	{
		title: '',
		maxHeight: '380px',
		showHeader: true,
		searchable: true,
		emptyText: ''
	}
);

const { t } = useI18n();
const dialogVisible = ref(false);
const isFormatted = ref(true);
const searchKey = ref('');

// 将输入内容转换为字符串
const rawString = computed<string>(() => {
	if (props.value === undefined || props.value === null || props.value === '') {
		return '';
	}
	if (typeof props.value === 'string') {
		const trimmed = props.value.trim();
		if (!trimmed) return '';
		return trimmed;
	}
	try {
		return JSON.stringify(props.value, null, 2);
	} catch {
		return String(props.value);
	}
});

const hasContent = computed(() => !!rawString.value && rawString.value !== '{}');

// 解析后的 JSON 字符串（格式化或压缩）
const displayString = computed(() => {
	if (!hasContent.value) return '';
	try {
		const parsed = typeof props.value === 'string' ? JSON.parse(props.value) : props.value;
		return isFormatted.value ? JSON.stringify(parsed, null, 2) : JSON.stringify(parsed);
	} catch {
		return rawString.value;
	}
});

const lineCount = computed(() => {
	if (!displayString.value) return 0;
	return displayString.value.split('\n').length;
});

function formatSize(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

// 语法着色逻辑
const highlightedHtml = computed(() => {
	const str = displayString.value;
	if (!str) return '';

	// 1. 转义 HTML 字符防注入
	const escaped = str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

	// 2. 预构建搜索高亮正则（仅作用于纯文本片段）
	const query = searchKey.value.trim();
	const searchReg = query ? new RegExp(`(${query.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')})`, 'gi') : null;

	// 3. 匹配 JSON Token 语义标记：回调内先对纯文本片段做搜索高亮再包语法 span，
	//    <mark> 只出现在文本节点内——搜索词命中 span/class 等标记名也不会破坏标签结构
	//    （标点/空白中的搜索词不高亮，可接受）。若先注入 mark 再跑语法正则，mark 标签
	//    属性中的带引号字符串会被当作 JSON string 二次包装导致结构碎裂。
	const html = escaped.replace(
		/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
		match => {
			let cls = 'json-hl-number';
			if (/^"/.test(match)) {
				if (/:$/.test(match)) {
					cls = 'json-hl-key';
				} else {
					cls = 'json-hl-string';
				}
			} else if (/true|false/.test(match)) {
				cls = 'json-hl-boolean';
			} else if (/null/.test(match)) {
				cls = 'json-hl-null';
			}
			const highlighted = searchReg ? match.replace(searchReg, '<mark class="json-hl-match">$1</mark>') : match;
			return `<span class="${cls}">${highlighted}</span>`;
		}
	);

	return html;
});

function handleCopy() {
	copyToClipboard(displayString.value, t('复制成功'), t('复制失败'));
}
</script>

<style lang="scss" scoped>
.log-json-viewer {
	position: relative;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	background: var(--el-bg-color-page);
	overflow: hidden;
	font-family:
		ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;

	&.is-empty {
		border-style: dashed;
	}

	&__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 6px 12px;
		background: var(--el-fill-color-light);
		border-bottom: 1px solid var(--el-border-color-lighter);
		font-size: 12px;

		.header-left {
			display: flex;
			align-items: center;
			gap: 8px;

			.meta-stat {
				color: var(--el-text-color-secondary);
				font-size: 11px;
			}
		}

		.header-actions {
			display: flex;
			align-items: center;
			gap: 4px;

			.search-input {
				width: 140px;
				margin-right: 4px;

				:deep(.el-input__wrapper) {
					border-radius: 12px;
					font-size: 12px;
				}
			}
		}
	}

	&__body {
		overflow-y: auto;
		overflow-x: auto;
	}

	.code-container {
		display: flex;
		min-width: 100%;
		font-size: 12px;
		line-height: 1.6;

		.line-numbers {
			padding: 10px 0;
			min-width: 38px;
			background: var(--el-fill-color-lighter);
			color: var(--el-text-color-placeholder);
			text-align: right;
			user-select: none;
			border-right: 1px solid var(--el-border-color-lighter);
			display: flex;
			flex-direction: column;

			span {
				padding: 0 8px;
				font-size: 11px;
			}
		}

		.code-content {
			flex: 1;
			padding: 10px 14px;
			overflow-x: auto;

			.highlight-code {
				margin: 0;
				font-family: inherit;
				font-size: 12px;
				white-space: pre-wrap;
				word-break: break-all;
			}
		}
	}

	.empty-placeholder {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 80px;
		color: var(--el-text-color-placeholder);
		font-size: 13px;
	}
}

.dialog-toolbar {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 12px;
	padding-bottom: 8px;
	border-bottom: 1px solid var(--el-border-color-lighter);

	.meta-stat {
		font-size: 12px;
		color: var(--el-text-color-secondary);
	}
}

.dialog-code-container {
	display: flex;
	height: 65vh;
	overflow-y: auto;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-bg-color-page);
	font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
	font-size: 13px;
	line-height: 1.6;

	.line-numbers {
		padding: 12px 0;
		min-width: 44px;
		background: var(--el-fill-color-lighter);
		color: var(--el-text-color-placeholder);
		text-align: right;
		user-select: none;
		border-right: 1px solid var(--el-border-color-lighter);
		display: flex;
		flex-direction: column;

		span {
			padding: 0 10px;
			font-size: 11px;
		}
	}

	.code-content {
		flex: 1;
		padding: 12px 16px;
		overflow-x: auto;

		.highlight-code {
			margin: 0;
			font-family: inherit;
			white-space: pre-wrap;
			word-break: break-all;
		}
	}
}

:deep(.json-hl-key) {
	color: #0284c7;
	font-weight: 600;
}

:deep(.json-hl-string) {
	color: #16a34a;
}

:deep(.json-hl-number) {
	color: #ea580c;
}

:deep(.json-hl-boolean) {
	color: #9333ea;
	font-weight: 600;
}

:deep(.json-hl-null) {
	color: var(--el-text-color-placeholder);
	font-style: italic;
}

:deep(.json-hl-match) {
	background-color: #fde047;
	color: #000;
	padding: 0 2px;
	border-radius: 2px;
}

html.dark {
	:deep(.json-hl-key) {
		color: #38bdf8;
	}

	:deep(.json-hl-string) {
		color: #4ade80;
	}

	:deep(.json-hl-number) {
		color: #fb923c;
	}

	:deep(.json-hl-boolean) {
		color: #c084fc;
	}

	:deep(.json-hl-match) {
		background-color: #ca8a04;
		color: #fff;
	}
}
</style>
