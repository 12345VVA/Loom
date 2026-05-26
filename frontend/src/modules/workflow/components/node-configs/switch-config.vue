<template>
	<el-form-item :label="$t('匹配变量名')" required>
		<el-input
			v-model="config.variable"
			placeholder="例如: status"
		/>
		<div class="field-hint">
			支持输入变量路径（如 variables.status 或 status）来进行值匹配。
		</div>
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
	<el-form-item :label="$t('Case 分支列表')">
		<div
			v-for="(item, index) in (config.cases || [])"
			:key="index"
			style="border: 1px solid #eee; padding: 10px; margin-bottom: 10px; border-radius: 6px; position: relative;"
		>
			<el-form-item :label="$t('匹配值 (Case Value)')" required style="margin-bottom: 8px;">
				<el-input v-model="item.value" placeholder="如: 1 或 success" size="small" />
			</el-form-item>
			<el-form-item :label="$t('目标路由')" required style="margin-bottom: 8px;">
				<el-select v-model="item.targetRoute" style="width: 100%" size="small">
					<el-option
						v-for="n in availableTargetNodes"
						:key="n.id"
						:label="n.label"
						:value="n.id"
					/>
				</el-select>
			</el-form-item>
			<el-button type="danger" size="small" link :icon="Delete" @click="config.cases.splice(index, 1)">
				{{ $t('删除此 Case') }}
			</el-button>
		</div>
		<el-button type="primary" size="small" plain :icon="Plus" style="width: 100%" @click="addCase">
			{{ $t('添加 Case 分支') }}
		</el-button>
	</el-form-item>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	availableTargetNodes: any[];
}>();

const config = props.modelValue;

function addCase() {
	if (!config.cases) {
		config.cases = [];
	}
	config.cases.push({ value: '', targetRoute: '' });
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
