<template>
	<el-form-item :label="$t('条件表达式 (Python)')" required>
		<el-input
			v-model="config.expression"
			placeholder="例如: len(variables.get('output')) > 100"
		/>
		<div class="field-hint">
			{{ $t('如果求值结果为 True，流转至 [分支 A]；反之流转至 [分支 B]') }}
		</div>
	</el-form-item>
	<el-form-item :label="$t('分支 A (满足条件)')" required>
		<el-select v-model="config.trueRoute" style="width: 100%">
			<el-option
				v-for="n in availableTargetNodes"
				:key="n.id"
				:label="n.label"
				:value="n.id"
			/>
		</el-select>
	</el-form-item>
	<el-form-item :label="$t('分支 B (不满足条件)')" required>
		<el-select v-model="config.falseRoute" style="width: 100%">
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
