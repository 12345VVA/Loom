<template>
	<iframe
		:src="iframeSrc"
		class="iframe"
		:class="{ 'is-hide': hide }"
		ref="iframeRef"
		sandbox="allow-forms allow-scripts allow-same-origin allow-popups allow-downloads"
		referrerpolicy="no-referrer"
	/>
</template>

<script setup lang="ts">
defineOptions({ name: 'base-ai-code-dev' });

import { computed, onMounted, onUnmounted, ref } from 'vue';
import { module } from '/@/cool';
import { isString } from 'lodash-es';
import { ctx } from 'virtual:ctx';

const props = defineProps({
	path: String,
	hide: Boolean
});

const emit = defineEmits(['message']);

const base = module.config('base');
const iframeRef = ref<HTMLIFrameElement | null>(null);
const event = new Map<string, (data: any) => void>();

const iframeSrc = computed(() => `${base.index}${props.path || ''}?lang=${ctx.serviceLang}`);

const targetOrigin = computed(() => {
	try {
		return new URL(iframeSrc.value, location.href).origin;
	} catch {
		return location.origin;
	}
});

function send(name: string, data: any, cb?: (data: any) => void) {
	if (cb) event.set(name, cb);
	iframeRef.value?.contentWindow?.postMessage({ name, data }, targetOrigin.value);
}

function onMessage(e: MessageEvent) {
	if (e.source !== iframeRef.value?.contentWindow || e.origin !== targetOrigin.value) {
		return;
	}

	try {
		const { name, data } = isString(e.data) ? JSON.parse(e.data) : e.data;

		const msg = event.get(name);
		if (msg) msg(data);

		emit('message', { name, data });
	} catch (error) {
		console.error('Invalid message data', error, e.data);
	}
}

onMounted(() => {
	window.addEventListener('message', onMessage);
});

onUnmounted(() => {
	window.removeEventListener('message', onMessage);
});

defineExpose({ send });
</script>

<style lang="scss" scoped>
.iframe.is-hide {
	height: 0;
	width: 0;
	opacity: 0;
	overflow: hidden;
}
</style>
