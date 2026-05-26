<template>
	<el-form-item :label="$t('AI 模型配置 (Profile)')" required>
		<el-select v-model="config.modelProfileCode" style="width: 100%">
			<el-option
				v-for="profile in profiles"
				:key="profile.code"
				:label="profile.name + ' (' + profile.code + ')'"
				:value="profile.code"
			/>
		</el-select>
	</el-form-item>
	<el-form-item :label="$t('Prompt 提示词模板')" required>
		<el-input
			v-model="config.promptTemplate"
			type="textarea"
			:rows="8"
			placeholder="支持使用变量插值。例如：请写一篇关于 {input_query} 的文章"
		/>
	</el-form-item>
	<el-form-item :label="$t('输出格式')">
		<el-select v-model="config.outputFormat" style="width: 100%">
			<el-option :label="$t('文本 (Text)')" value="text" />
			<el-option :label="$t('JSON 对象')" value="json" />
		</el-select>
		<div class="field-hint">JSON 模式下自动解析 LLM 返回的结构化数据，下游可用 {变量名.字段} 访问子字段。</div>
	</el-form-item>
	<template v-if="config.outputFormat === 'json'">
		<el-form-item :label="$t('JSON 输出字段')">
			<div class="field-hint" style="margin-bottom: 8px;">定义期望 LLM 返回的 JSON 字段，系统自动追加格式指令到提示词末尾。</div>
			<div
				v-for="(field, idx) in (config.jsonFields || [])"
				:key="idx"
				style="display: flex; gap: 6px; margin-bottom: 6px; align-items: center;"
			>
				<el-input v-model="field.name" placeholder="字段名" style="width: 30%" />
				<el-input v-model="field.description" placeholder="说明 (可选)" style="flex: 1" />
				<el-button :icon="Delete" circle size="small" @click="removeJsonField(idx)" />
			</div>
			<el-button type="primary" link @click="addJsonField">
				<el-icon><Plus /></el-icon> {{ $t('添加字段') }}
			</el-button>
		</el-form-item>
	</template>
	<el-form-item :label="$t('输出变量写入')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: output" />
	</el-form-item>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
}>();

const config = props.modelValue;

function addJsonField() {
	if (!config.jsonFields) {
		config.jsonFields = [];
	}
	config.jsonFields.push({ name: '', description: '' });
}

function removeJsonField(index: number) {
	const fields = config.jsonFields || [];
	fields.splice(index, 1);
}
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}
</style>
