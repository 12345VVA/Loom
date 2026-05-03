<template>
	<div class="ai-image-test">
		<section class="generator">
			<header class="toolbar">
				<cl-select
					v-model="form.profileCode"
					:options="profileOptions"
					:placeholder="$t('默认图片配置')"
					clearable
					:width="260"
				/>
				<el-input v-model="form.scenario" :placeholder="$t('场景')" clearable />
				<cl-select v-model="form.size" :options="sizeOptions" :width="140" />
				<cl-select v-model="form.responseFormat" :options="responseFormatOptions" :width="140" />
				<el-switch v-model="form.watermark" :active-text="$t('水印')" />
			</header>

			<div class="prompt">
				<el-input
					v-model="form.prompt"
					type="textarea"
					:rows="5"
					:placeholder="$t('输入图片生成提示词')"
				/>
			</div>

			<div class="advanced">
				<div class="advanced__head">
					<span>{{ $t('高级参数 JSON') }}</span>
					<el-button text type="primary" @click="resetOptions">{{ $t('重置') }}</el-button>
				</div>
				<el-input v-model="form.optionsText" type="textarea" :rows="8" />
			</div>

			<footer class="actions">
				<el-button @click="clearResult">{{ $t('清空结果') }}</el-button>
				<el-button :loading="loading.submit" type="warning" @click="submitTask">{{ $t('异步提交') }}</el-button>
				<el-button :loading="loading.generate" type="primary" @click="generate">{{ $t('生成图片') }}</el-button>
			</footer>
		</section>

		<aside class="result">
			<header>
				<span>{{ $t('生成结果') }}</span>
				<el-tag v-if="imageItems.length" size="small" type="success">{{ imageItems.length }}</el-tag>
			</header>

			<div class="preview-list">
				<div v-for="(item, index) in imageItems" :key="index" class="preview-item">
					<el-image
						class="preview-image"
						:src="item.src"
						fit="contain"
						:preview-src-list="previewUrls"
						:initial-index="index"
						preview-teleported
					/>
					<div class="preview-actions">
						<el-button text type="primary" @click="copyText(item.value)">{{ $t('复制') }}</el-button>
						<el-button v-if="item.url" text type="primary" @click="openUrl(item.url)">{{ $t('打开') }}</el-button>
					</div>
				</div>
				<el-empty v-if="!imageItems.length" :description="$t('暂无图片')" />
			</div>

			<el-tabs class="raw-tabs">
				<el-tab-pane :label="$t('请求')">
					<pre>{{ formatJson(lastPayload) }}</pre>
				</el-tab-pane>
				<el-tab-pane :label="$t('响应')">
					<pre>{{ formatJson(result) }}</pre>
				</el-tab-pane>
			</el-tabs>
		</aside>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-image'
});

import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const aiService = service.ai as any;

const profileOptions = ref<{ label: string; value: string }[]>([]);
const result = ref<any>(null);
const lastPayload = ref<any>(null);
const loading = reactive({
	generate: false,
	submit: false
});
const form = reactive({
	profileCode: '',
	scenario: 'default',
	prompt: '一张未来感 AI 内容平台海报，干净的构图，科技感灯光，高质量细节',
	size: '2560x1440',
	responseFormat: 'url',
	watermark: true,
	optionsText: '{}'
});

const sizeOptions = [
	{ label: '2048x2048', value: '2048x2048' },
	{ label: '2304x1728', value: '2304x1728' },
	{ label: '1728x2304', value: '1728x2304' },
	{ label: '2560x1440', value: '2560x1440' },
	{ label: '1440x2560', value: '1440x2560' },
	{ label: '2496x1664', value: '2496x1664' },
	{ label: '1664x2496', value: '1664x2496' }
];
const responseFormatOptions = [
	{ label: 'url', value: 'url' },
	{ label: 'b64_json', value: 'b64_json' }
];

const imageItems = computed(() => extractImageItems(result.value));
const previewUrls = computed(() => imageItems.value.map(item => item.src));

onMounted(() => {
	loadProfiles();
});

async function loadProfiles() {
	const res = await (service.ai.profile as any).list({
		modelType: 'image',
		status: true
	});
	profileOptions.value = (res || []).map((item: any) => ({
		label: `${item.name || item.code} / ${item.modelName || item.modelId}`,
		value: item.code
	}));
}

function buildPayload() {
	const prompt = form.prompt.trim();
	if (!prompt) {
		ElMessage.warning(t('请输入提示词'));
		return null;
	}

	let advanced = {};
	try {
		advanced = form.optionsText.trim() ? JSON.parse(form.optionsText) : {};
	} catch (err: any) {
		ElMessage.error(`${t('高级参数 JSON 格式错误')}: ${err.message}`);
		return null;
	}

	return {
		scenario: form.scenario || 'default',
		profileCode: form.profileCode || undefined,
		prompt,
		options: {
			size: form.size,
			response_format: form.responseFormat,
			watermark: form.watermark,
			...advanced
		}
	};
}

async function generate() {
	const payload = buildPayload();
	if (!payload) {
		return;
	}

	loading.generate = true;
	lastPayload.value = payload;
	try {
		result.value = await aiService.runtime.model.image(payload);
		if (!extractImageItems(result.value).length) {
			ElMessage.warning(t('调用成功，但未解析到图片'));
		}
	} catch (err: any) {
		ElMessage.error(err.message || t('生成失败'));
	} finally {
		loading.generate = false;
	}
}

async function submitTask() {
	const payload = buildPayload();
	if (!payload) {
		return;
	}

	loading.submit = true;
	lastPayload.value = {
		taskType: 'image',
		scenario: payload.scenario,
		profileCode: payload.profileCode,
		payload: {
			prompt: payload.prompt,
			options: payload.options
		}
	};
	try {
		const res = await aiService.runtime.model.submitTask(lastPayload.value);
		result.value = res;
		ElMessage.success(t('提交成功'));
	} catch (err: any) {
		ElMessage.error(err.message || t('提交失败'));
	} finally {
		loading.submit = false;
	}
}

function resetOptions() {
	form.optionsText = '{}';
}

function clearResult() {
	result.value = null;
	lastPayload.value = null;
}

async function copyText(value: string) {
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制'));
}

function openUrl(url: string) {
	window.open(url, '_blank');
}

function formatJson(value: any) {
	if (!value) {
		return '-';
	}
	return JSON.stringify(value, null, 2);
}

function extractImageItems(value: any): { src: string; value: string; url?: string }[] {
	const items = findImageData(value);
	return items
		.map(item => {
			const url = item?.url || item?.image_url || item?.imageUrl;
			const b64 = item?.b64_json || item?.b64Json || item?.base64;
			if (url) {
				return { src: url, value: url, url };
			}
			if (b64) {
				const src = String(b64).startsWith('data:image') ? String(b64) : `data:image/png;base64,${b64}`;
				return { src, value: String(b64) };
			}
			return null;
		})
		.filter(Boolean) as { src: string; value: string; url?: string }[];
}

function findImageData(value: any): any[] {
	if (!value) {
		return [];
	}
	if (typeof value === 'string') {
		try {
			return findImageData(JSON.parse(value));
		} catch {
			return [];
		}
	}
	if (Array.isArray(value)) {
		return value;
	}
	if (Array.isArray(value.data)) {
		return value.data;
	}
	if (value.resultPayload) {
		return findImageData(value.resultPayload);
	}
	if (value.raw) {
		const rawItems = findImageData(value.raw);
		if (rawItems.length) {
			return rawItems;
		}
	}
	if (value.result) {
		return findImageData(value.result);
	}
	if (Array.isArray(value.images)) {
		return value.images;
	}
	return [];
}
</script>

<style lang="scss" scoped>
.ai-image-test {
	display: grid;
	grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
	gap: 12px;
	height: 100%;
	min-height: 640px;
}

.generator,
.result {
	display: flex;
	min-height: 0;
	border: 1px solid var(--el-border-color-light);
	background: var(--el-bg-color);
}

.generator {
	flex-direction: column;
}

.toolbar {
	display: grid;
	grid-template-columns: 1fr;
	gap: 10px;
	padding: 12px;
	border-bottom: 1px solid var(--el-border-color-light);
}

.prompt,
.advanced,
.actions {
	padding: 12px;
}

.advanced {
	border-top: 1px solid var(--el-border-color-lighter);

	&__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 8px;
		font-weight: 600;
	}
}

.actions {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
	margin-top: auto;
	border-top: 1px solid var(--el-border-color-light);
}

.result {
	flex-direction: column;

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px;
		border-bottom: 1px solid var(--el-border-color-light);
		font-weight: 600;
	}
}

.preview-list {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 12px;
	min-height: 280px;
	max-height: 50vh;
	overflow: auto;
	padding: 12px;
}

.preview-item {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-blank);
}

.preview-image {
	display: block;
	width: 100%;
	height: 220px;
	background: var(--el-fill-color-lighter);
}

.preview-actions {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
	padding: 8px;
}

.raw-tabs {
	min-height: 0;
	padding: 0 12px 12px;

	pre {
		max-height: 260px;
		margin: 0;
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 12px;
	}
}

@media (max-width: 960px) {
	.ai-image-test {
		grid-template-columns: 1fr;
		height: auto;
	}
}
</style>
