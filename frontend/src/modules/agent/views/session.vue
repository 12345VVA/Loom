<template>
	<!-- cl-crud 骨架承载权限指令（页面本体为交互式会话，非标准表格） -->
	<cl-crud ref="Crud">
		<chat-workspace mode="standalone" class="agent-session-workspace" />
	</cl-crud>
</template>

<script lang="ts" setup name="agent-session">
import { useCrud } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import ChatWorkspace from '../components/chat-workspace.vue';

const { service } = useCool();

// 无需调用 app.refresh()，避免无表格渲染时向后端发送无效的分页请求
const Crud = useCrud({ service: service.agent.session });
</script>

<style lang="scss" scoped>
.agent-session-workspace {
	height: calc(100vh - 120px);
	border-radius: 6px;
	overflow: hidden;
}
</style>
