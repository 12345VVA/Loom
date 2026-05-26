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
	<el-form-item :label="$t('默认路由 (无匹配时)')" required>
		<el-select v-model="config.defaultRoute" style="width: 100%">
			<el-option
				v-for="n in availableTargetNodes"
				:key="n.id"
				:label="n.label"
				:value="n.id"
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
			<el-form-item :label="$t('目标路由')" required style="margin-bottom: 8px;">
				<el-select v-model="intent.targetRoute" style="width: 100%" size="small">
					<el-option
						v-for="n in availableTargetNodes"
						:key="n.id"
						:label="n.label"
						:value="n.id"
					/>
				</el-select>
			</el-form-item>
			<el-button type="danger" size="small" link :icon="Delete" @click="config.intents.splice(index, 1)">
				{{ $t('删除此意图') }}
			</el-button>
		</div>
		<el-button type="primary" size="small" plain :icon="Plus" style="width: 100%" @click="addIntent">
			{{ $t('添加意图') }}
		</el-button>
	</el-form-item>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
	availableTargetNodes: any[];
}>();

const config = props.modelValue;

function addIntent() {
	if (!config.intents) {
		config.intents = [];
	}
	config.intents.push({ name: '', description: '', targetRoute: '' });
}
</script>
