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

	<node-config-section :title="$t('系统提示词')">
		<el-form-item style="margin-bottom: 0">
			<cl-editor-markdown
				v-model="config.systemPromptTemplate"
				:height="180"
				simple
				placeholder="用于设定大模型角色、背景约束、输出格式等，支持使用变量插值。例如：你是一个经验丰富的前端工程师..."
			/>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('用户提示词')">
		<el-form-item required style="margin-bottom: 0">
			<cl-editor-markdown
				v-model="config.promptTemplate"
				:height="220"
				simple
				placeholder="用户当前输入的具体问题或任务，支持使用变量插值。例如：请帮我写一段关于 {input_query} 的代码"
			/>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('输出')" :tooltip="$t('定义模型输出的内容及变量名')">
		<template #actions>
			<el-dropdown
				trigger="click"
				popper-class="wf-output-format-dropdown"
				@command="config.outputFormat = $event"
			>
				<span class="output-format-btn">
					<el-tooltip placement="top" effect="dark" :show-after="200">
						<template #content>
							<div style="max-width: 200px; line-height: 1.4">
								<template v-if="config.outputFormat === 'json'">
									Schema 约束模式：系统自动生成 JSON Schema 约束模型输出，下游可用
									{变量名.字段} 访问子字段。
								</template>
								<template v-else-if="config.outputFormat === 'json_object'">
									宽松模式：要求模型输出合法 JSON，但不限定 Schema。需在 Prompt
									中描述所需 JSON 结构。
								</template>
								<template v-else> 普通文本输出。 </template>
							</div>
						</template>
						<el-icon><InfoFilled /></el-icon>
					</el-tooltip>
					<span style="margin: 0 4px"
						>{{ $t('输出格式') }}
						{{
							config.outputFormat === 'json'
								? 'JSON'
								: config.outputFormat === 'json_object'
									? 'JSON(宽松)'
									: '文本'
						}}</span
					>
					<el-icon><ArrowDown /></el-icon>
				</span>
				<template #dropdown>
					<el-dropdown-menu>
						<el-dropdown-item
							command="text"
							:class="{ 'is-active': config.outputFormat === 'text' }"
							>{{ $t('文本') }}</el-dropdown-item
						>
						<el-dropdown-item
							command="json"
							:class="{ 'is-active': config.outputFormat === 'json' }"
							>{{ $t('JSON') }}</el-dropdown-item
						>
						<el-dropdown-item
							command="json_object"
							:class="{ 'is-active': config.outputFormat === 'json_object' }"
							>{{ $t('JSON (宽松)') }}</el-dropdown-item
						>
					</el-dropdown-menu>
				</template>
			</el-dropdown>

			<template v-if="config.outputFormat === 'json'">
				<div class="json-actions-divider"></div>
				<el-tooltip placement="top" :content="$t('导入 JSON')">
					<span class="action-icon-btn" @click="jsonEditorRef?.openImportDialog()">
						<el-icon><upload /></el-icon>
					</span>
				</el-tooltip>
				<el-tooltip placement="top" :content="$t('复制 JSON')">
					<span class="action-icon-btn" @click="jsonEditorRef?.copyJson()">
						<el-icon><document-copy /></el-icon>
					</span>
				</el-tooltip>
				<el-tooltip placement="top" :content="$t('添加根字段')">
					<span class="action-icon-btn primary" @click="jsonEditorRef?.addRootNode()">
						<el-icon><plus /></el-icon>
					</span>
				</el-tooltip>
			</template>
		</template>

		<template v-if="config.outputFormat === 'json'">
			<cl-json-tree-editor
				ref="jsonEditorRef"
				v-model="config.jsonFields"
				mode="schema"
				:hide-footer="true"
			/>
		</template>

		<el-form-item
			:label="$t('输出变量写入')"
			required
			:style="{ marginTop: config.outputFormat === 'json' ? '16px' : '0' }"
		>
			<el-input v-model="config.outputVariable" placeholder="默认: output" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Upload, DocumentCopy, Plus } from '@element-plus/icons-vue';
import ClJsonTreeEditor from '../cl-json-tree-editor.vue';
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
}>();

const config = props.modelValue;
const jsonEditorRef = ref<InstanceType<typeof ClJsonTreeEditor>>();
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}
</style>

<!-- 非 scoped：dropdown 菜单被传送至 body，scoped 样式无法命中 -->
<style lang="scss">
.wf-output-format-dropdown .el-dropdown-menu__item.is-active {
	color: var(--el-color-primary);
	font-weight: 600;
}
</style>
