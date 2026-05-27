<template>
	<el-form-item :label="$t('批处理列表变量名')" required>
		<el-input v-model="config.batchListVariable" placeholder="默认: batch_list_variable" />
	</el-form-item>
	<el-form-item :label="$t('单项变量名')">
		<el-input v-model="config.itemVariable" placeholder="默认: batch_item" />
	</el-form-item>
	<el-form-item :label="$t('并发上限')" required>
		<el-input-number v-model="config.concurrencyLimit" :min="1" :max="20" style="width: 100%" />
	</el-form-item>
	<el-form-item :label="$t('结果输出变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: batch_results" />
	</el-form-item>
	<el-form-item :label="$t('循环体入口节点')" required>
		<el-select v-model="config.loopBodyRoute" style="width: 100%">
			<el-option
				v-for="n in availableTargetNodes"
				:key="n.id"
				:label="n.label"
				:value="n.id"
			/>
		</el-select>
	</el-form-item>
	<el-form-item :label="$t('循环结束跳转节点')" required>
		<el-select v-model="config.exitRoute" style="width: 100%">
			<el-option
				v-for="n in availableTargetNodes"
				:key="n.id"
				:label="n.label"
				:value="n.id"
			/>
		</el-select>
	</el-form-item>
</template>

<script setup lang="ts">
const props = defineProps<{
	modelValue: Record<string, any>;
	availableTargetNodes: any[];
}>();

const config = props.modelValue;
</script>
