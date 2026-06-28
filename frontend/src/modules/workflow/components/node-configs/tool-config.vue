<template>
	<node-config-hint style="margin-bottom: 8px">
		<el-tag type="warning" size="small">{{ $t('此节点类型已弃用') }}</el-tag>
		<span style="margin-left: 6px">{{
			$t('建议使用「工具执行器」节点替代，以获得更好的功能和维护支持。')
		}}</span>
	</node-config-hint>
	<node-config-section :title="$t('工具配置')">
		<el-form-item :label="$t('指定运行的工具')" required style="margin-bottom: 0">
			<el-select v-model="config.toolName" style="width: 100%">
				<el-option :label="$t('网页搜索 (Search)')" value="web_search" />
				<el-option :label="$t('文件读写 (FileSystem)')" value="file_system" />
				<el-option :label="$t('计算器 (Calculator)')" value="calculator" />
			</el-select>
		</el-form-item>
	</node-config-section>
	<node-config-section :title="$t('输出')">
		<el-form-item :label="$t('输出变量写入')" required style="margin-bottom: 0">
			<el-input v-model="config.outputVariable" placeholder="默认: tool_result" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import NodeConfigSection from './node-config-section.vue';
import NodeConfigHint from './node-config-hint.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;
</script>
