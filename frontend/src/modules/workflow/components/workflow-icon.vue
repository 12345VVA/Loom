<template>
	<svg
		class="workflow-icon"
		:class="[`workflow-icon--${name}`, className]"
		:style="computedStyle"
		:viewBox="viewBox"
		xmlns="http://www.w3.org/2000/svg"
		aria-hidden="true"
	>
		<!-- 1. 抽屉标题日志图标 -->
		<g v-if="name === 'log'">
			<rect
				x="3"
				y="3"
				width="18"
				height="18"
				rx="4"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<path
				d="M7 8h10M7 12h7M7 16h9"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
			/>
		</g>

		<!-- 2. 耗时秒表图标 -->
		<g v-else-if="name === 'timer'">
			<circle cx="12" cy="13" r="8" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M12 9v4l2.5 2.5"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
			<path
				d="M10 2h4M12 2v3"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
			/>
		</g>

		<!-- 3. 图片/产物画廊图标 (多层照片) -->
		<g v-else-if="name === 'images' || name === 'gallery' || name === 'image_generator'">
			<rect
				x="3"
				y="3"
				width="18"
				height="18"
				rx="3.5"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<circle cx="8.5" cy="8.5" r="1.8" fill="currentColor" />
			<path
				d="M21 15l-5-5L5 21"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 4. 大模型 (LLM) 双星芒 Sparkles -->
		<g v-else-if="name === 'llm' || name === 'sparkles'">
			<path
				d="M12 2C12 6.5 15.5 10 20 10C15.5 10 12 13.5 12 18C12 13.5 8.5 10 4 10C8.5 10 12 6.5 12 2Z"
				fill="currentColor"
			/>
			<path
				d="M18.5 14C18.5 16 19.8 17.5 21.5 17.5C19.8 17.5 18.5 19 18.5 21C18.5 19 17.2 17.5 15.5 17.5C17.2 17.5 18.5 16 18.5 14Z"
				fill="currentColor"
			/>
		</g>

		<!-- 5. 循环控制 (Loop) 双向圆润箭头 -->
		<g v-else-if="name === 'loop_controller' || name === 'loop'">
			<path
				d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M3 3v5h5"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M16 16h5v5"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 6. 变量转换 (Variable Transform) 流转重组 -->
		<g v-else-if="name === 'variable_transform' || name === 'transform'">
			<path
				d="M4 7h11a4 4 0 0 1 4 4v0a4 4 0 0 1-4 4H4"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M7 4L4 7l3 3"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M17 20l3-3-3-3"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 7. 变量赋值 (Variable Assignment) 数据注入 -->
		<g v-else-if="name === 'variable_assignment' || name === 'assignment'">
			<rect
				x="3"
				y="4"
				width="18"
				height="16"
				rx="3"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<path
				d="M7 10h4M7 14h6M15 10l3 2-3 2"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 8. 条件判断 (Condition) 分流菱形决策 -->
		<g v-else-if="name === 'condition'">
			<path
				d="M12 3l8 9-8 9-8-9 8-9z"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linejoin="round"
				fill="none"
			/>
			<circle cx="12" cy="12" r="2" fill="currentColor" />
		</g>

		<!-- 9. 条件分支 (Switch) 多路路由 -->
		<g v-else-if="name === 'switch'">
			<circle cx="5" cy="12" r="2.5" stroke="currentColor" stroke-width="1.8" fill="none" />
			<circle cx="19" cy="6" r="2.5" stroke="currentColor" stroke-width="1.8" fill="none" />
			<circle cx="19" cy="18" r="2.5" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M7.5 12h4c1.5 0 3-.8 4-2.2L16.5 8"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				fill="none"
			/>
			<path
				d="M11.5 12c1.5 0 3 .8 4 2.2l1 1.6"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				fill="none"
			/>
		</g>

		<!-- 10. 工具执行 (Tool Executor) 齿轮/扳手 -->
		<g v-else-if="name === 'tool_executor' || name === 'tool'">
			<path
				d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 11. 人工确认 (Human Input) 审核印章/用户 -->
		<g v-else-if="name === 'human_input'">
			<circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M5.5 20a6.5 6.5 0 0 1 13 0"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				fill="none"
			/>
			<circle cx="18" cy="14" r="3" fill="#ef4444" />
			<path
				d="M17 14l.8.8 1.5-1.5"
				stroke="#fff"
				stroke-width="1.2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 12. 意图分类 (Intent Classifier) 芯片微处理 -->
		<g v-else-if="name === 'intent_classifier'">
			<rect
				x="5"
				y="5"
				width="14"
				height="14"
				rx="3"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<circle cx="12" cy="12" r="2.5" fill="currentColor" />
			<path
				d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
			/>
		</g>

		<!-- 13. 开始节点 (Start) 圆环三角 -->
		<g v-else-if="name === 'start'">
			<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none" />
			<polygon points="10 8 16 12 10 16 10 8" fill="currentColor" />
		</g>

		<!-- 14. 结束节点 (End) 旗帜目标 -->
		<g v-else-if="name === 'end'">
			<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M9 12l2 2 4-4"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 15. 批处理器 (Batch) 叠层卡片 -->
		<g v-else-if="name === 'batch_processor'">
			<rect
				x="7"
				y="7"
				width="13"
				height="13"
				rx="2"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<path
				d="M4 17V5a2 2 0 0 1 2-2h12"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				fill="none"
			/>
		</g>

		<!-- 16. 下载图标 (Download) -->
		<g v-else-if="name === 'download'">
			<path
				d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<polyline
				points="7 10 12 15 17 10"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<line
				x1="12"
				y1="15"
				x2="12"
				y2="3"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		</g>

		<!-- 17. 输出终端图标 (Output) -->
		<g v-else-if="name === 'output'">
			<rect
				x="3"
				y="4"
				width="18"
				height="16"
				rx="3"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<path
				d="M7 10l3 2-3 2M13 14h4"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 18. 输入数据流图标 (Input) -->
		<g v-else-if="name === 'input'">
			<rect
				x="3"
				y="4"
				width="18"
				height="16"
				rx="3"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<path
				d="M11 9l-3 3 3 3M8 12h8"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 19. 内容预览/文案阅读图标 (Preview) -->
		<g v-else-if="name === 'preview'">
			<path
				d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M9 7h6M9 11h4"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
			/>
		</g>

		<!-- 20. 异常警告图标 (Error) -->
		<g v-else-if="name === 'error' || name === 'danger'">
			<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M12 8v4M12 16h.01"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
			/>
		</g>

		<!-- 21. 成功图标 (Success) -->
		<g v-else-if="name === 'success' || name === 'check'">
			<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M8 12l2.5 2.5 5.5-5.5"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 22. 复制图标 (Copy) -->
		<g v-else-if="name === 'copy' || name === 'copy_document'">
			<rect
				x="9"
				y="9"
				width="12"
				height="12"
				rx="2.5"
				stroke="currentColor"
				stroke-width="1.8"
				fill="none"
			/>
			<path
				d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 23. 全屏查看 (Fullscreen) -->
		<g v-else-if="name === 'fullscreen'">
			<path
				d="M15 3h6v6M9 21H3v-6M21 9l-7 7M3 15l7-7"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<path
				d="M3 9V3h6M21 15v6h-6"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 24. 退出全屏 (Fullscreen Exit / Aim) -->
		<g v-else-if="name === 'fullscreen_exit' || name === 'exit_fullscreen'">
			<path
				d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 25. 关闭图标 (Close) -->
		<g v-else-if="name === 'close'">
			<path
				d="M18 6L6 18M6 6l12 12"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		</g>

		<!-- 26. 搜索图标 (Search) -->
		<g v-else-if="name === 'search'">
			<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M21 21l-4.35-4.35"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
			/>
		</g>

		<!-- 27. 折叠/展开箭头 (Arrow Right) -->
		<g v-else-if="name === 'arrow_right' || name === 'arrow'">
			<path
				d="M9 18l6-6-6-6"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>

		<!-- 28. 新窗口打开 (External / Top Right) -->
		<g v-else-if="name === 'external' || name === 'top_right'">
			<path
				d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<polyline
				points="15 3 21 3 21 9"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
			<line
				x1="10"
				y1="14"
				x2="21"
				y2="3"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		</g>

		<!-- 29. 压缩/格式化操作 (Compress / Format / Operation) -->
		<g v-else-if="name === 'compress' || name === 'format' || name === 'operation'">
			<circle cx="6" cy="6" r="2" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M8 6h12M4 12h16M4 18h16"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
			/>
		</g>

		<!-- 30. 加载中微动旋转 (Loading) -->
		<g v-else-if="name === 'loading'">
			<path
				d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
			/>
		</g>

		<!-- 31. 默认兜底图标 (Gear/Default) -->
		<g v-else>
			<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8" fill="none" />
			<path
				d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				fill="none"
			/>
		</g>
	</svg>
</template>

<script setup lang="ts">
import { computed } from 'vue';

defineOptions({ name: 'workflow-icon' });

const props = withDefaults(
	defineProps<{
		name: string;
		size?: number | string;
		color?: string;
		className?: string;
		viewBox?: string;
	}>(),
	{
		size: '1em',
		color: 'currentColor',
		className: '',
		viewBox: '0 0 24 24'
	}
);

const computedStyle = computed(() => {
	const parsedSize = typeof props.size === 'number' ? `${props.size}px` : props.size;
	return {
		width: parsedSize,
		height: parsedSize,
		color: props.color
	};
});
</script>

<style lang="scss" scoped>
.workflow-icon {
	display: inline-block;
	vertical-align: middle;
	flex-shrink: 0;
	transition:
		transform 0.2s ease,
		color 0.2s ease;
}
</style>
