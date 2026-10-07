<template>
	<div class="variable-transform-config">
		<node-config-section :title="$t('转换配置')">
			<el-form-item :label="$t('输入变量')" required style="margin-bottom: 0">
				<cl-variable-input
					v-model="config.inputVariable"
					scope="global"
					placeholder="例如: loop_results"
				/>
			</el-form-item>

			<el-form-item :label="$t('转换动作')" required>
				<el-select v-model="config.transformType" style="width: 100%">
					<el-option label="数组拼接为文本 (Join Array)" value="join_array" />
					<el-option
						label="提取 JSON 字段 (Extract JSON Path)"
						value="extract_json_path"
					/>
					<el-option label="执行自定义表达式 (Eval Expression)" value="eval_expression" />
				</el-select>
			</el-form-item>

			<el-form-item v-if="config.transformType === 'join_array'" :label="$t('分隔符')">
				<el-input v-model="config.transformArgs.separator" placeholder="默认为 ," />
			</el-form-item>

			<el-form-item
				v-if="config.transformType === 'extract_json_path'"
				:label="$t('JSON 路径 (Path)')"
				required
			>
				<cl-variable-input
					v-model="config.transformArgs.path"
					:show-variable-btn="false"
					placeholder="例如: data.user.name"
				/>
				<div style="font-size: 12px; color: #999; line-height: 1.2; margin-top: 4px">
					{{ $t('支持点号访问和数组下标，如 items.0.title') }}
				</div>
			</el-form-item>

			<el-form-item
				v-if="config.transformType === 'eval_expression'"
				:label="$t('Python 表达式')"
				required
			>
				<cl-variable-input
					v-model="config.transformArgs.expression"
					scope="global"
					type="textarea"
					:rows="3"
					placeholder="例如: ', '.join(input_value)"
				/>
				<div style="font-size: 12px; color: #999; line-height: 1.2; margin-top: 4px">
					{{
						$t(
							'使用 input_value 引用输入变量的值。支持简单的 Python 函数调用如 len() 等。'
						)
					}}
				</div>
			</el-form-item>
		</node-config-section>

		<node-config-section :title="$t('输出')">
			<el-form-item :label="$t('输出变量写入')" required style="margin-bottom: 0">
				<el-input v-model="config.outputVariable" placeholder="例如: transformed_value" />
			</el-form-item>
		</node-config-section>
	</div>
</template>

<script setup lang="ts">
import ClVariableInput from '../cl-variable-input.vue';
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

// 三期B7（WF-P2-9）存量键迁移：本类型曾是前端唯一 snake_case 配置面板，打开旧图时
// 把 snake 键归一化为 camelCase（与其他节点一致）；后端编译期 convert_keys_to_snake
// 对 camel 自动转换，未打开面板直接运行的存量图不受影响（snake 原文照常执行）。
const SNAKE_TO_CAMEL: ReadonlyArray<readonly [string, string]> = [
	['input_variable', 'inputVariable'],
	['transform_type', 'transformType'],
	['transform_args', 'transformArgs'],
	['output_variable', 'outputVariable']
];
for (const [snake, camel] of SNAKE_TO_CAMEL) {
	if (config[camel] === undefined && config[snake] !== undefined) {
		config[camel] = config[snake];
		delete config[snake];
	}
}

if (!config.transformArgs) {
	config.transformArgs = {};
}
</script>
