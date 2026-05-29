<template>
	<div class="variable-transform-config">
		<el-form-item :label="$t('输入变量')" required>
			<el-input v-model="config.input_variable" placeholder="例如: loop_results" />
		</el-form-item>
		
		<el-form-item :label="$t('转换动作')" required>
			<el-select v-model="config.transform_type" style="width: 100%">
				<el-option label="数组拼接为文本 (Join Array)" value="join_array" />
				<el-option label="提取 JSON 字段 (Extract JSON Path)" value="extract_json_path" />
				<el-option label="执行自定义表达式 (Eval Expression)" value="eval_expression" />
			</el-select>
		</el-form-item>

		<el-form-item v-if="config.transform_type === 'join_array'" :label="$t('分隔符')">
			<el-input v-model="config.transform_args.separator" placeholder="默认为 ," />
		</el-form-item>

		<el-form-item v-if="config.transform_type === 'extract_json_path'" :label="$t('JSON 路径 (Path)')" required>
			<el-input v-model="config.transform_args.path" placeholder="例如: data.user.name" />
			<div style="font-size: 12px; color: #999; line-height: 1.2; margin-top: 4px">
				{{ $t('支持点号访问和数组下标，如 items.0.title') }}
			</div>
		</el-form-item>
		
		<el-form-item v-if="config.transform_type === 'eval_expression'" :label="$t('Python 表达式')" required>
			<el-input v-model="config.transform_args.expression" type="textarea" :rows="3" placeholder="例如: ', '.join(input_value)" />
			<div style="font-size: 12px; color: #999; line-height: 1.2; margin-top: 4px">
				{{ $t('使用 input_value 引用输入变量的值。支持简单的 Python 函数调用如 len() 等。') }}
			</div>
		</el-form-item>

		<el-form-item :label="$t('输出写入变量')" required>
			<el-input v-model="config.output_variable" placeholder="例如: transformed_value" />
		</el-form-item>
	</div>
</template>

<script setup lang="ts">
const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

if (!config.transform_args) {
	config.transform_args = {};
}
</script>
