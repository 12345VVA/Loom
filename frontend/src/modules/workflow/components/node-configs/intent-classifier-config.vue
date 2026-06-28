<template>
	<node-config-section :title="$t('模型')">
		<el-form-item :label="$t('AI 模型配置 (Profile)')" required style="margin-bottom: 0">
			<el-select v-model="config.modelProfileCode" style="width: 100%">
				<el-option
					v-for="profile in profiles"
					:key="profile.code"
					:label="profile.name + ' (' + profile.code + ')'"
					:value="profile.code"
				/>
			</el-select>
		</el-form-item>
	</node-config-section>
	<node-config-section :title="$t('意图分类')">
		<el-form-item style="margin-bottom: 0">
			<div
				v-for="(intent, index) in config.intents || []"
				:key="index"
				style="
					border: 1px solid #eee;
					padding: 10px;
					margin-bottom: 10px;
					border-radius: 6px;
					position: relative;
				"
			>
				<el-form-item :label="$t('意图名称')" required style="margin-bottom: 8px">
					<el-input v-model="intent.name" placeholder="例如: 翻译" size="small" />
				</el-form-item>
				<el-form-item :label="$t('描述')" style="margin-bottom: 8px">
					<el-input
						v-model="intent.description"
						placeholder="意图判定依据"
						size="small"
					/>
				</el-form-item>
				<el-button
					type="danger"
					size="small"
					link
					:icon="Delete"
					@click="removeIntent(index)"
				>
					{{ $t('删除此意图') }}
				</el-button>
			</div>
			<el-button
				type="primary"
				size="small"
				plain
				:icon="Plus"
				style="width: 100%"
				@click="addIntent"
			>
				{{ $t('添加意图') }}
			</el-button>
			<node-config-hint style="margin-top: 8px">
				<span>{{
					$t(
						'添加意图后，节点右侧自动生成对应端口，从端口直接连线到目标节点。未匹配任何意图时走"默认"端口。'
					)
				}}</span>
			</node-config-hint>
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';
import NodeConfigHint from './node-config-hint.vue';
import NodeConfigSection from './node-config-section.vue';
import { useVueFlow } from '@vue-flow/core';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
	nodeId?: string;
}>();

const config = props.modelValue;
const { getEdges, removeEdges } = useVueFlow();

function addIntent() {
	if (!config.intents) {
		config.intents = [];
	}
	config.intents.push({ name: '', description: '' });
}

function removeIntent(index: number) {
	if (props.nodeId) {
		const edges = getEdges.value;
		const edgeToRemove = edges.find(
			(e) => e.source === props.nodeId && e.sourceHandle === `intent_${index}`
		);
		if (edgeToRemove) {
			removeEdges([edgeToRemove.id]);
		}
		edges.forEach((e) => {
			if (e.source === props.nodeId && e.sourceHandle && e.sourceHandle.startsWith('intent_')) {
				const idx = parseInt(e.sourceHandle.replace('intent_', ''));
				if (idx > index) {
					e.sourceHandle = `intent_${idx - 1}`;
				}
			}
		});
	}
	config.intents.splice(index, 1);
}
</script>
