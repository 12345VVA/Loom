<template>
	<div class="agent-welcome">
		<div class="agent-welcome__header">
			<div class="agent-welcome__avatar">
				<el-icon><opportunity /></el-icon>
			</div>
			<h2 class="agent-welcome__name">{{ profile?.name || t('agent.workspace.title') }}</h2>
			<p class="agent-welcome__desc">
				{{ profile?.description || t('agent.session.newChatHint') }}
			</p>
		</div>

		<div v-if="starters.length" class="agent-welcome__starters">
			<div class="agent-welcome__starters-title">
				<el-icon><chat-line-round /></el-icon>
				<span>{{ t('agent.workspace.suggestedPrompts') }}</span>
			</div>
			<div class="agent-welcome__cards">
				<div
					v-for="(starter, idx) in starters"
					:key="idx"
					class="starter-card"
					@click="emit('select-starter', starter)"
				>
					<div class="starter-card__text">{{ starter }}</div>
					<el-icon class="starter-card__arrow"><arrow-right /></el-icon>
				</div>
			</div>
		</div>
	</div>
</template>

<script lang="ts" setup name="agent-welcome">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { Opportunity, ChatLineRound, ArrowRight } from '@element-plus/icons-vue';

const props = defineProps<{
	profile?: {
		id: number;
		name: string;
		description?: string;
		executionMode?: string;
	} | null;
}>();

const emit = defineEmits<{
	(e: 'select-starter', prompt: string): void;
}>();

const { t } = useI18n();

const starters = computed(() => {
	if (!props.profile) return [];
	return [
		t('agent.workspace.starter1'),
		t('agent.workspace.starter2'),
		t('agent.workspace.starter3')
	];
});
</script>

<style lang="scss" scoped>
.agent-welcome {
	width: 100%;
	padding: 36px 0 24px;
	display: flex;
	flex-direction: column;
	align-items: center;
	animation: fadeIn 0.3s ease-in-out;

	&__header {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		margin-bottom: 32px;
	}

	&__avatar {
		width: 56px;
		height: 56px;
		border-radius: 16px;
		background: linear-gradient(135deg, var(--el-color-primary-light-3), var(--el-color-primary));
		display: flex;
		align-items: center;
		justify-content: center;
		color: #fff;
		font-size: 28px;
		box-shadow: 0 4px 14px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.28);
		margin-bottom: 16px;
	}

	&__name {
		font-size: 20px;
		font-weight: 600;
		color: var(--el-text-color-primary);
		margin: 0 0 10px;
		letter-spacing: 0.2px;
	}

	&__desc {
		font-size: 14px;
		color: var(--el-text-color-secondary);
		line-height: 1.6;
		margin: 0;
		max-width: 540px;
	}

	&__starters {
		width: 100%;
		text-align: left;
	}

	&__starters-title {
		font-size: 13px;
		color: var(--el-text-color-placeholder);
		display: flex;
		align-items: center;
		gap: 6px;
		margin-bottom: 14px;
		font-weight: 500;
	}

	&__cards {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 12px;

		@media (max-width: 900px) {
			grid-template-columns: 1fr;
		}
	}
}

.starter-card {
	background-color: var(--el-fill-color-blank);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	padding: 14px 16px;
	cursor: pointer;
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	min-height: 68px;
	box-sizing: border-box;
	transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);

	&:hover {
		border-color: var(--el-color-primary-light-3);
		background-color: var(--el-color-primary-light-9);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.1);

		.starter-card__arrow {
			color: var(--el-color-primary);
			transform: translateX(3px);
		}
	}

	&__text {
		font-size: 13px;
		color: var(--el-text-color-regular);
		line-height: 1.5;
		flex: 1;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		word-break: break-word;
	}

	&__arrow {
		color: var(--el-text-color-placeholder);
		font-size: 14px;
		transition: all 0.2s ease;
		flex-shrink: 0;
	}
}

@keyframes fadeIn {
	from {
		opacity: 0;
		transform: translateY(8px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}
</style>
