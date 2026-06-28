<template>
	<node-config-section :title="$t('工具配置')">
		<el-form-item :label="$t('选择系统工具')" required style="margin-bottom: 0;">
			<el-select v-model="config.toolCode" style="width: 100%">
				<el-option :label="$t('网页搜索 (web_search)')" value="web_search" />
				<el-option :label="$t('本地文件系统读写 (file_system)')" value="file_system" />
			</el-select>
		</el-form-item>
	</node-config-section>
	<node-config-section :title="$t('参数设置')">
		<el-form-item :label="$t('工具参数 JSON')" required style="margin-bottom: 0;">
			<cl-editor-codemirror v-model="config.argumentsJson" :height="200" />
			<div class="field-hint">支持以 "variables.变量名" 级联绑定上下文值。</div>
		</el-form-item>
	</node-config-section>
	<node-config-section :title="$t('输出')">
		<el-form-item :label="$t('输出变量写入')" required style="margin-bottom: 0;">
			<el-input v-model="config.outputVariable" placeholder="默认: tool_result" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import NodeConfigSection from './node-config-section.vue';
const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}
</style>
