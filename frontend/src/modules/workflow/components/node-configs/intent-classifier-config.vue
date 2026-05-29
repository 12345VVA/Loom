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
	<el-form-item :label="$t('意图分流列表')">
		<div
			v-for="(intent, index) in (config.intents || [])"
			:key="index"
			style="border: 1px solid #eee; padding: 10px; margin-bottom: 10px; border-radius: 6px; position: relative;"
		>
			<el-form-item :label="$t('意图名称')" required style="margin-bottom: 8px;">
				<el-input v-model="intent.name" placeholder="例如: 翻译" size="small" />
			</el-form-item>
			<el-form-item :label="$t('描述')" style="margin-bottom: 8px;">
				<el-input v-model="intent.description" placeholder="意图判定依据" size="small" />
			</el-form-item>
			<el-button type="danger" size="small" link :icon="Delete" @click="config.intents.splice(index, 1)">
				{{ $t('删除此意图') }}
			</el-button>
		</div>
		<el-button type="primary" size="small" plain :icon="Plus" style="width: 100%" @click="addIntent">
			{{ $t('添加意图') }}
		</el-button>
		<div class="config-hint">
			<el-icon><info-filled /></el-icon>
			<span>{{ $t('添加意图后，节点右侧自动生成对应端口，从端口直接连线到目标节点。未匹配任何意图时走"默认"端口。') }}</span>
		</div>
	</el-form-item>
</template>

<script setup lang="ts">
import { Delete, Plus, InfoFilled } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
}>();

const config = props.modelValue;

function addIntent() {
	if (!config.intents) {
		config.intents = [];
	}
	config.intents.push({ name: '', description: '' });
}
</script>

<style scoped>
.config-hint {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	margin-top: 8px;
	font-size: 12px;
	color: var(--el-text-color-placeholder);
	line-height: 1.4;
}
</style>
