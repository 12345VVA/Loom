<template>
	<div style="padding: 20px">
		<h3>基础用法 (编辑器模式)</h3>
		<cl-editor-markdown v-model="mdValue" :height="400" />

		<h3 style="margin-top: 20px">纯预览/渲染模式 (onlyPreview)</h3>
		<div
			style="
				border: 1px solid var(--el-border-color);
				padding: 15px;
				border-radius: 4px;
				background: var(--el-bg-color-blank);
			"
		>
			<cl-editor-markdown v-model="mdValue" onlyPreview />
		</div>

		<h3 style="margin-top: 20px">禁用状态 (disabled)</h3>
		<cl-editor-markdown v-model="mdValue" disabled :height="300" />

		<h3 style="margin-top: 20px">通过 cl-editor 包装使用</h3>
		<cl-editor name="cl-editor-markdown" v-model="mdValue" :height="350" />
	</div>
</template>

<script lang="ts" setup>
import { ref } from 'vue';

const mdValue = ref(
	`# Loom Markdown 编辑器/渲染器

基于 \`md-editor-v3\` 封装的 Markdown 组件。

## 功能特性
- **实时预览**：支持双栏或者独立窗口预览。
- **丰富的 Markdown 语法**：支持数学公式、流程图、代码高亮等。
- **文件上传**：无缝对接 Cool-Admin 文件上传钩子，拖拽或粘贴图片即可上传。

### 代码高亮示例
\`\`\`typescript
const isCool = true;
if (isCool) {
  console.log("Welcome to Loom!");
}
\`\`\`

### 列表与表格
1. 项 1
2. 项 2
   - 子项 A
   - 子项 B

| 框架 | 版本 | 核心技术 |
| :--- | :--- | :--- |
| Loom 前端 | 8.0.0 | Vue 3 + TS + Element Plus |
| Loom 后端 | 1.0.0 | FastAPI + SQLModel |
`
);
</script>
