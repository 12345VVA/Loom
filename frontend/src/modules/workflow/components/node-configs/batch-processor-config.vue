<template>
	<el-form-item :label="$t('批处理列表变量名')" required>
		<el-input v-model="config.batchListVariable" placeholder="默认: batch_list_variable" />
		<div class="field-hint">当前版本固化从状态变量 batch_list_variable 读入。</div>
	</el-form-item>
	<el-form-item :label="$t('并发上限限制')" required>
		<el-input-number v-model="config.concurrencyLimit" :min="1" :max="20" style="width: 100%" />
	</el-form-item>
	<el-form-item :label="$t('并发任务大模型 (Profile)')" required>
		<el-select v-model="config.actionTemplate.config.modelProfileCode" style="width: 100%">
			<el-option
				v-for="profile in profiles"
				:key="profile.code"
				:label="profile.name + ' (' + profile.code + ')'"
				:value="profile.code"
			/>
		</el-select>
	</el-form-item>
	<el-form-item :label="$t('并发 Prompt 模板')" required>
		<cl-editor-markdown v-model="config.actionTemplate.config.promptTemplate" :height="220" simple placeholder="例如：请翻译单词 {item}" />
	</el-form-item>
	<el-form-item :label="$t('结果输出变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: batch_results" />
	</el-form-item>
</template>

<script setup lang="ts">
const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
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
