<template>
	<el-form-item :label="$t('循环数组变量名')" required>
		<el-input v-model="config.listVariable" placeholder="默认: list_variable" />
		<div class="field-hint">当前版本固化读取状态中的 list_variable。</div>
	</el-form-item>
	<el-form-item :label="$t('单项变量名')" required>
		<el-input v-model="config.itemVariable" placeholder="默认: loop_item" />
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

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}
</style>
