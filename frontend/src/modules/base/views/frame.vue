<template>
	<div v-loading="loading" class="page-iframe" :element-loading-text="$t('拼命加载中')">
		<iframe
			v-if="url"
			:ref="setRefs('iframe')"
			:src="url"
			frameborder="0"
			sandbox="allow-forms allow-scripts allow-popups allow-downloads"
			referrerpolicy="no-referrer"
		></iframe>
		<div v-else class="iframe-blocked">{{ errorMessage }}</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'frame-web'
});

import { ref, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';

const loading = ref(false);
const url = ref('');
const errorMessage = ref('');

const { route, refs, setRefs } = useCool();

// 校验 iframe URL：仅允许 http/https 协议，禁止 javascript:/data:/blob: 等危险协议
function validateIframeUrl(raw: unknown): string {
	if (typeof raw !== 'string' || !raw) return '';
	let parsed: URL;
	try {
		parsed = new URL(raw, window.location.href);
	} catch {
		return '';
	}
	if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
		return '';
	}
	return parsed.href;
}

watch(
	() => route,
	val => {
		const raw = val.meta?.iframeUrl;
		// 无 iframeUrl 属正常情况（该路由本就不是 iframe 容器）：静默置空，不报错。
		// 仅当显式配置了 iframeUrl 却非法（协议不允许/解析失败）时才提示，避免把"无值"误判为"非法"。
		if (!raw) {
			url.value = '';
			errorMessage.value = '';
			return;
		}
		const safe = validateIframeUrl(raw);
		url.value = safe;
		if (!safe) {
			errorMessage.value = 'iframe 地址不合法，已阻止加载';
			ElMessage.error(errorMessage.value);
		} else {
			errorMessage.value = '';
		}
	},
	{
		immediate: true,
		deep: true
	}
);

onMounted(() => {
	if (url.value && refs.iframe) {
		loading.value = true;

		refs.iframe.onload = () => {
			loading.value = false;
		};
	}
});
</script>

<style lang="scss" scoped>
.page-iframe {
	height: 100%;

	iframe {
		height: 100%;
		width: 100%;
	}

	.iframe-blocked {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: #909399;
		font-size: 14px;
	}
}
</style>
