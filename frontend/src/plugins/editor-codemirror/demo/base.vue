<template>
	<div style="padding: 20px">
		<h3>基础用法</h3>
		<cl-editor-codemirror v-model="jsonValue" :height="400" />

		<h3 style="margin-top: 20px">预览模式</h3>
		<cl-editor-codemirror v-model="jsonValue" preview :height="200" />

		<h3 style="margin-top: 20px">禁用状态</h3>
		<cl-editor-codemirror v-model="jsonValue" disabled :height="200" />

		<h3 style="margin-top: 20px">通过 cl-editor 包装使用</h3>
		<cl-editor name="cl-editor-codemirror" v-model="jsonValue" :height="300" />
	</div>
</template>

<script lang="ts" setup>
import { ref } from 'vue';

const jsonValue = ref(
	JSON.stringify(
		{
			name: 'Loom',
			version: '8.0.0',
			features: ['Vue 3', 'TypeScript', 'Vite'],
			config: {
				theme: 'default',
				darkMode: false
			}
		},
		null,
		2
	)
);
</script>
