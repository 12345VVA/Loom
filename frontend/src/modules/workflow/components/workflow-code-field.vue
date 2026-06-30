<template>
	<el-input :model-value="model" readonly :placeholder="$t('保存后自动生成')">
		<template #append>
			<el-tooltip :content="$t('复制编码')" placement="top">
				<el-button :icon="CopyDocument" :disabled="!model" @click="onCopy" />
			</el-tooltip>
		</template>
	</el-input>
</template>

<script lang="ts" setup>
import { useI18n } from 'vue-i18n';
import { CopyDocument } from '@element-plus/icons-vue';
import { copyToClipboard } from '../utils';

const { t } = useI18n();

// cool-admin upsert 经 v-model（modelValue + update:modelValue）注入 code 值
const model = defineModel<string>({ default: '' });

function onCopy() {
	if (!model.value) return;
	copyToClipboard(model.value, t('编码已复制'));
}
</script>

<style lang="scss" scoped>
:deep(.el-input) {
	width: 100%;
}
</style>
