<template>
	<el-form-item :label="$t('生图大模型配置 (Profile)')" required>
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
		<cl-editor-markdown v-model="config.promptTemplate" :height="220" simple placeholder="支持插值变量，例如：画一张关于 {topic} 的图片" />
	</el-form-item>
	<el-form-item :label="$t('图片尺寸 (size)')" required>
		<el-select v-model="config.size" style="width: 100%">
			<el-option label="256x256" value="256x256" />
			<el-option label="512x512" value="512x512" />
			<el-option label="1024x1024" value="1024x1024" />
		</el-select>
	</el-form-item>
	<el-form-item :label="$t('图片 URL 写入变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: image_url" />
	</el-form-item>
</template>

<script setup lang="ts">
const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
}>();

const config = props.modelValue;
</script>
