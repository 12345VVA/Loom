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
				:placeholder="$t('用于设定大模型角色、背景约束、输出格式等，支持使用变量插值。例如：你是一个经验丰富的前端工程师...')"
			/>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('用户提示词')">
		<el-form-item :label="$t('提示词内容')" required style="margin-bottom: 0">
			<cl-editor-markdown
				v-model="config.promptTemplate"
				:height="220"
				simple
				:placeholder="$t('用户当前输入的具体问题或任务，支持使用变量插值。例如：请帮我写一段关于 {input_query} 的代码')"
			/>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('多模态图片输入')">
		<el-form-item style="margin-bottom: 0">
			<el-radio-group v-model="imageInputMode" size="small" style="margin-bottom: 6px">
				<el-radio-button value="none">{{ $t('无') }}</el-radio-button>
				<el-radio-button value="variable">{{ $t('变量引用') }}</el-radio-button>
				<el-radio-button value="template">{{ $t('模板渲染') }}</el-radio-button>
			</el-radio-group>

			<el-select
				v-if="imageInputMode === 'variable'"
				v-model="config.imageVariables"
				multiple
				filterable
				allow-create
				default-first-option
				clearable
				style="width: 100%"
				:placeholder="$t('选择上游图片变量（可多选）')"
			>
				<el-option
					v-for="opt in imageVariableOptions"
					:key="opt.value"
					:label="opt.label"
					:value="opt.value"
				/>
			</el-select>
			<el-input
				v-if="imageInputMode === 'template'"
				v-model="config.imageTemplate"
				:placeholder="$t('模板字符串，例如：{image_url}')"
			/>

			<div class="field-hint">{{ $t('绑定的图片将与提示词一起发送给模型（需具备视觉能力的多模态模型）') }}</div>
			<div v-if="!selectedProfileSupportsVision" class="field-hint vision-warning">
				{{ $t('当前模型可能不支持视觉输入，建议切换多模态模型') }}
			</div>
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
			:style="{ marginTop: config.outputFormat === 'json' ? '16px' : '0' }"
		>
			<el-input v-model="config.outputVariable" :placeholder="$t('默认: output')" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Upload, DocumentCopy, Plus } from '@element-plus/icons-vue';
import ClJsonTreeEditor from '../cl-json-tree-editor.vue';
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
	upstreamVariables?: { variableName: string; nodeLabel?: string; variableType?: string }[];
}>();

const config = props.modelValue;
const jsonEditorRef = ref<InstanceType<typeof ClJsonTreeEditor>>();

// WFI-2d：多模态图片输入（imageVariables 多选优先 / imageTemplate 模板兜底，
// 与生图节点参考图惯例一致）。mode 为显式状态（computed setter 方案在清空互斥键后
// 会因目标键为空立即回落 'none'，切不进 template——见 llm-config.test.ts 用例）
const imageInputMode = ref<'none' | 'variable' | 'template'>(
	(Array.isArray(config.imageVariables) && config.imageVariables.length > 0) || config.imageTemplate
		? Array.isArray(config.imageVariables) && config.imageVariables.length > 0
			? 'variable'
			: 'template'
		: 'none'
);
watch(imageInputMode, mode => {
	if (mode !== 'variable') config.imageVariables = [];
	if (mode !== 'template') config.imageTemplate = '';
});

const imageVariableOptions = computed(() => {
	const vars = props.upstreamVariables || [];
	const imageVars = vars.filter(v => v.variableType === 'image');
	const pool = imageVars.length > 0 ? imageVars : vars;
	return pool.map(v => ({
		label: v.nodeLabel ? `${v.nodeLabel} / ${v.variableName}` : v.variableName,
		value: v.variableName
	}));
});

// 软警示：profile 数据带能力标签且明确不含 vision 时提示（以后端校验为准）
const selectedProfileSupportsVision = computed(() => {
	const p = props.profiles.find((item: any) => item.code === config.modelProfileCode) as any;
	if (!p) return true;
	const caps = String(
		p.modelCapabilities || p.capabilities || p.model_capabilities || ''
	).toLowerCase();
	if (!caps) return true; // 无能力信息不警示
	return caps.split(',').some((c: string) => c.trim() === 'vision');
});
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.vision-warning {
	color: var(--el-color-warning);
}
</style>

<!-- 非 scoped：dropdown 菜单被传送至 body，scoped 样式无法命中 -->
<style lang="scss">
.wf-output-format-dropdown .el-dropdown-menu__item.is-active {
	color: var(--el-color-primary);
	font-weight: 600;
}
</style>
