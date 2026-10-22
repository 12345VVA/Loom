<script setup lang="ts">
// 组装预览（透明组装，设计 5.1）：warnings 横幅 + prompt 全文复制 + 片段/参考图元信息。
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { useClipboard } from '@vueuse/core';

export interface ComposerPreviewPayload {
	prompt: string;
	negativePrompt?: string;
	referenceImages?: string[];
	effectiveSize?: string | null;
	warnings?: { code: string; message: string; level: string }[];
	composedPromptHash?: string;
	composerVersion?: string;
	segments?: { source: string; text: string; included: boolean }[];
	referenceSegments?: { mediaId: number; role?: string | null; included: boolean; skipReason?: string }[];
}

const props = defineProps<{ result: ComposerPreviewPayload | null }>();

const { t } = useI18n();
const { copy } = useClipboard();

const warnings = computed(() => props.result?.warnings ?? []);
const includedSegments = computed(() => (props.result?.segments ?? []).filter((s) => s.included));

async function copyPrompt() {
	if (!props.result?.prompt) return;
	await copy(props.result.prompt);
	ElMessage.success(t('已复制组装结果'));
}

const sourceLabels: Record<string, string> = {
	style: '风格',
	scene: '场景',
	character: '角色',
	user: '正文'
};
</script>

<template>
	<div v-if="result" class="composer-preview">
		<el-alert
			v-for="w in warnings"
			:key="w.code + w.message"
			:title="w.message"
			:type="w.level === 'info' ? 'info' : 'warning'"
			:closable="false"
			class="warn"
		/>

		<div class="block">
			<div class="head">
				<span class="label">{{ $t('组装结果') }}</span>
				<el-button link size="small" @click="copyPrompt">{{ $t('复制') }}</el-button>
			</div>
			<pre class="prompt">{{ result.prompt || $t('（空）') }}</pre>
		</div>

		<div v-if="result.negativePrompt" class="block">
			<div class="head"><span class="label">{{ $t('负面词') }}</span></div>
			<pre class="prompt neg">{{ result.negativePrompt }}</pre>
		</div>

		<div v-if="result.referenceImages?.length" class="block">
			<div class="head"><span class="label">{{ $t('参考图') }}</span></div>
			<div class="refs">
				<el-image
					v-for="(url, i) in result.referenceImages"
					:key="i"
					:src="url"
					:preview-src-list="result.referenceImages"
					fit="cover"
					class="ref-thumb"
				/>
			</div>
		</div>

		<div class="meta">
			<span v-if="result.effectiveSize">size: {{ result.effectiveSize }}</span>
			<el-tag v-for="seg in includedSegments" :key="seg.source" size="small" class="seg">
				{{ $t(sourceLabels[seg.source] || seg.source) }}
			</el-tag>
			<span v-if="result.composedPromptHash" class="hash">
				{{ $t('指纹') }} {{ result.composedPromptHash }} (v{{ result.composerVersion }})
			</span>
		</div>
	</div>
</template>

<style scoped>
.composer-preview {
	display: flex;
	flex-direction: column;
	gap: 8px;
}
.warn {
	--el-alert-padding: 6px 10px;
}
.block .head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 4px;
}
.label {
	font-size: 12px;
	color: var(--el-text-color-secondary);
}
.prompt {
	margin: 0;
	padding: 8px;
	background: var(--el-fill-color-light);
	border-radius: 6px;
	font-size: 12px;
	white-space: pre-wrap;
	word-break: break-all;
	max-height: 140px;
	overflow: auto;
}
.prompt.neg {
	color: var(--el-text-color-secondary);
}
.refs {
	display: flex;
	gap: 8px;
	flex-wrap: wrap;
}
.ref-thumb {
	width: 64px;
	height: 64px;
	border-radius: 6px;
}
.meta {
	display: flex;
	align-items: center;
	gap: 8px;
	flex-wrap: wrap;
	font-size: 12px;
	color: var(--el-text-color-secondary);
}
.hash {
	font-family: monospace;
}
</style>
