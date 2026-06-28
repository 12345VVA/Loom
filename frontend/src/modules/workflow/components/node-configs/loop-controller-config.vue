<template>
	<node-config-section :title="$t('基础配置')">
		<el-form-item :label="$t('循环列表变量名')" required style="margin-bottom: 0">
			<el-input v-model="config.listVariable" placeholder="默认: list_variable" />
			<div class="field-hint">当前版本固化读取状态中的 list_variable。</div>
		</el-form-item>
		<el-form-item :label="$t('单项变量名')" required style="margin-top: 18px; margin-bottom: 0">
			<el-input v-model="config.itemVariable" placeholder="默认: loop_item" />
		</el-form-item>

		<node-config-hint style="margin-top: 16px">
			<span>循环体容器已自动创建，将节点拖入容器即可加入循环体。</span>
		</node-config-hint>
	</node-config-section>
	<node-config-section :title="$t('输出')">
		<el-form-item :label="$t('输出变量写入')" required style="margin-bottom: 0">
			<el-input v-model="config.outputVariable" placeholder="默认: loop_results" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import NodeConfigSection from './node-config-section.vue';
import NodeConfigHint from './node-config-hint.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	availableTargetNodes: any[];
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
