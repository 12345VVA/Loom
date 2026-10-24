<template>
	<!-- cl-crud 骨架承载权限指令（页面本体为交互式会话，非标准表格） -->
	<cl-crud ref="Crud">
		<ChatWorkspace mode="standalone" class="agent-session-workspace" />
	</cl-crud>
</template>

<script lang="ts" setup name="agent-session">
import { useCrud } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import ChatWorkspace from '../components/chat-workspace.vue';

const { service } = useCool();

const Crud = useCrud({ service: service.agent.session }, (app) => {
	app.service.refresh();
});
</script>

<style lang="scss" scoped>
.agent-session-workspace {
	height: calc(100vh - 120px);
	border-radius: 6px;
	overflow: hidden;
}
</style>
