<template>
	<node-config-section :title="$t('输出')" :tooltip="$t('定义工作流的最终输出内容及格式')">
		<template #actions>
			<el-dropdown trigger="click" popper-class="wf-output-format-dropdown" @command="config.outputFormat = $event">
				<span class="output-format-btn">
					<el-tooltip placement="top" effect="dark" :show-after="200">
						<template #content>
							<div style="max-width: 200px; line-height: 1.4;">
								<template v-if="config.outputFormat === 'json'">
									JSON 对象输出模式，可定义结构化字段。
								</template>
								<template v-else>
									普通文本输出模式，支持 Markdown。
								</template>
							</div>
						</template>
						<el-icon><InfoFilled /></el-icon>
					</el-tooltip>
					<span style="margin: 0 4px;">{{ $t('输出格式') }} {{ config.outputFormat === 'json' ? 'JSON' : '文本' }}</span>
					<el-icon><ArrowDown /></el-icon>
				</span>
				<template #dropdown>
					<el-dropdown-menu>
						<el-dropdown-item command="text" :class="{ 'is-active': config.outputFormat === 'text' }">{{ $t('纯文本') }}</el-dropdown-item>
						<el-dropdown-item command="json" :class="{ 'is-active': config.outputFormat === 'json' }">{{ $t('JSON 对象') }}</el-dropdown-item>
					</el-dropdown-menu>
				</template>
			</el-dropdown>
			
			<template v-if="config.outputFormat === 'json'">
				<div class="json-actions-divider"></div>
				<el-tooltip placement="top" :content="$t('导入 JSON')">
					<span class="action-icon-btn" @click="jsonEditorRef?.openImportDialog()">
						<el-icon><Upload /></el-icon>
					</span>
				</el-tooltip>
				<el-tooltip placement="top" :content="$t('复制 JSON')">
					<span class="action-icon-btn" @click="jsonEditorRef?.copyJson()">
						<el-icon><DocumentCopy /></el-icon>
					</span>
				</el-tooltip>
				<el-tooltip placement="top" :content="$t('添加根字段')">
					<span class="action-icon-btn primary" @click="jsonEditorRef?.addRootNode()">
						<el-icon><Plus /></el-icon>
					</span>
				</el-tooltip>
			</template>
		</template>

		<!-- JSON 模式：结构化字段编辑器 -->
		<template v-if="config.outputFormat === 'json'">
			<div class="field-hint" style="margin-bottom: 8px;">定义工作流输出的 JSON 字段，值支持变量引用如 {变量名}。</div>
			<cl-json-tree-editor ref="jsonEditorRef" v-model="config.outputFields" mode="value" :hide-footer="true" />
			
			<el-form-item v-if="endNodeJsonPreview" :label="$t('JSON 预览')" style="margin-top: 16px; margin-bottom: 0;">
				<pre class="json-preview-block">{{ endNodeJsonPreview }}</pre>
			</el-form-item>
		</template>

		<!-- 文本模式 -->
		<template v-if="config.outputFormat === 'text'">
			<div class="field-hint" style="margin-bottom: 8px;">使用 {变量名} 引用上游变量，渲染结果作为纯文本输出。</div>
			<cl-editor-markdown v-model="config.outputTemplate" :height="260" placeholder="支持使用变量插值。例如：最终结果为 {LLM节点_output}" />
		</template>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { InfoFilled, ArrowDown, Upload, DocumentCopy, Plus } from '@element-plus/icons-vue';
import ClJsonTreeEditor from '../cl-json-tree-editor.vue';
import NodeConfigSection from './node-config-section.vue';

const jsonEditorRef = ref<InstanceType<typeof ClJsonTreeEditor>>();

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

function buildJson(children: any[]): any {
	const obj: Record<string, any> = {};
	for (const child of children) {
		if (!child.name) continue;
		if (child.type === 'object') {
			obj[child.name] = buildJson(child.children || []);
		} else if (child.type === 'array') {
			obj[child.name] = buildArray(child.children || []);
		} else {
			obj[child.name] = child.value || '';
		}
	}
	return obj;
}

function buildArray(children: any[]): any[] {
	return (children || []).map(child => {
		if (child.type === 'object') {
			return buildJson(child.children || []);
		} else if (child.type === 'array') {
			return buildArray(child.children || []);
		} else {
			return child.value || '';
		}
	});
}

const endNodeJsonPreview = computed(() => {
	const fields = config.outputFields || [];
	if (fields.length === 0) return '';
	const obj = buildJson(fields);
	return JSON.stringify(obj, null, 2);
});
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.json-preview-block {
	width: 100%;
	box-sizing: border-box;
	background: #f5f7fa;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 4px;
	padding: 10px;
	font-size: 12px;
	max-height: 200px;
	overflow: auto;
	white-space: pre-wrap;
	margin: 0;
	color: var(--el-text-color-regular);
}
</style>

<!-- 非 scoped：dropdown 菜单被传送至 body，scoped 样式无法命中 -->
<style lang="scss">
.wf-output-format-dropdown .el-dropdown-menu__item.is-active {
	color: var(--el-color-primary);
	font-weight: 600;
}
</style>
