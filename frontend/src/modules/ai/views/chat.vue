<template>
	<div class="ai-chat-workbench" :class="{ 'with-stream-open': showStreamDrawer }">
		<!-- 主对话工作区 -->
		<section class="chat-container">
			<!-- 顶部工具栏 -->
			<header class="chat-header">
				<div class="header-left">
					<div class="title-badge">
						<el-icon class="title-icon"><chat-dot-round /></el-icon>
						<span class="title-text">{{ $t('对话测试') }}</span>
					</div>

					<cl-select
						v-model="form.profileCode"
						:options="profileOptions"
						:placeholder="$t('默认调用配置')"
						clearable
						:width="240"
					/>
				</div>

				<div class="header-right">
					<!-- 高级推理参数 Popover 抽离组件 -->
					<chat-params-popover :form="form" />

					<el-button
						:type="showStreamDrawer ? 'primary' : 'default'"
						plain
						size="small"
						@click="showStreamDrawer = !showStreamDrawer"
					>
						<el-icon class="mr-2"><data-analysis /></el-icon>
						{{ $t('流调试') }}
					</el-button>

					<el-button link size="small" @click="clearMessages">
						<el-icon class="mr-2"><delete /></el-icon>
						{{ $t('清屏') }}
					</el-button>
				</div>
			</header>

			<!-- 消息历史滚动区 -->
			<div ref="messagesContainer" class="messages-flow">
				<!-- 空状态：欢迎卡片与灵感卡片 -->
				<div v-if="!messages.length" class="empty-chat-welcome">
					<div class="welcome-avatar">
						<el-icon><magic-stick /></el-icon>
					</div>
					<h2 class="welcome-title">{{ $t('开启 AI 智能对话') }}</h2>
					<p class="welcome-desc">
						{{ $t('已就绪！在下方输入您的问题或指令，支持流式实时打字与 Markdown 富文本排版。') }}
					</p>

					<div class="sample-prompts-grid">
						<div
							v-for="(item, idx) in SAMPLE_QUESTIONS"
							:key="idx"
							class="sample-card"
							@click="useSamplePrompt(item.prompt)"
						>
							<div class="sample-icon">
								<component :is="item.icon" />
							</div>
							<div class="sample-content">
								<div class="sample-title">{{ item.title }}</div>
								<div class="sample-sub">{{ item.prompt }}</div>
							</div>
						</div>
					</div>
				</div>

				<!-- 消息气泡流：独立抽离组件 -->
				<chat-message-bubble
					v-for="item in messages"
					:key="item.id"
					:message="item"
					:is-streaming="isStreamingCurrent(item.id)"
					:loading="isStreamingCurrent(item.id) || (loading.chat && item.role === 'assistant' && !item.content)"
					@regenerate="regenerateFrom"
					@remove="removeMessage"
				/>
			</div>

			<!-- 底部输入栏：独立抽离组件 -->
			<chat-composer
				ref="composerRef"
				v-model="prompt"
				:is-busy="isBusy"
				:loading="loading"
				@send-chat="sendChat"
				@send-stream="sendStream"
				@stop-stream="stopStream"
			/>
		</section>

		<!-- 右侧：通用 SSE 流调试侧边抽屉 -->
		<ai-stream-drawer
			v-model="showStreamDrawer"
			:events="streamEvents"
			:status="streamStatus"
			:status-type="streamStatusType"
			@clear="clearStreamLogs"
			@copy="copyStreamLogs"
		/>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-chat'
});

import { onMounted, ref } from 'vue';
import {
	ChatDotRound,
	Delete,
	DataAnalysis,
	MagicStick,
	Edit,
	Document,
	Reading,
	Search
} from '@element-plus/icons-vue';
import { useChatWorkbench } from '../composables/use-chat-workbench';
import ChatParamsPopover from '../components/chat-params-popover.vue';
import ChatMessageBubble from '../components/chat-message-bubble.vue';
import ChatComposer from '../components/chat-composer.vue';
import AiStreamDrawer from '../components/ai-stream-drawer.vue';

const {
	profileOptions,
	prompt,
	messagesContainer,
	messages,
	streamEvents,
	streamStatus,
	streamStatusType,
	showStreamDrawer,
	loading,
	isBusy,
	form,
	isStreamingCurrent,
	initProfiles,
	sendChat,
	sendStream,
	stopStream,
	removeMessage,
	regenerateFrom,
	clearMessages,
	clearStreamLogs,
	copyStreamLogs
} = useChatWorkbench();

const composerRef = ref();

const SAMPLE_QUESTIONS = [
	{
		title: '文案润色与改写',
		prompt: '请将以下产品简介润色得更有吸引力，语气专业且富有科技感：\n[在此粘贴文本]',
		icon: Edit
	},
	{
		title: '代码生成与分析',
		prompt: '用 TypeScript 和 Vue 3 组合式 API 实现一个带有倒计时的防抖搜索输入组件。',
		icon: Document
	},
	{
		title: '长文总结提炼',
		prompt: '阅读并归纳以下内容的核心要点，使用清晰的 Markdown 结构列出核心结论与行动清单：',
		icon: Reading
	},
	{
		title: '头脑风暴构思',
		prompt: '我正在设计一款 AI 原生的企业内容管理平台，请提供 5 个差异化的创新功能点。',
		icon: Search
	}
];

function useSamplePrompt(text: string) {
	prompt.value = text;
	composerRef.value?.focus();
}

onMounted(() => {
	initProfiles();
});
</script>

<style lang="scss" scoped>
.ai-chat-workbench {
	display: flex;
	height: calc(100vh - 110px);
	min-height: 600px;
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	overflow: hidden;
	box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);

	.chat-container {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		height: 100%;
	}

	.chat-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 18px;
		background: var(--el-fill-color-blank);
		border-bottom: 1px solid var(--el-border-color-lighter);
		flex-shrink: 0;

		.header-left {
			display: flex;
			align-items: center;
			gap: 12px;

			.title-badge {
				display: flex;
				align-items: center;
				gap: 6px;
				font-size: 15px;
				font-weight: 600;
				color: var(--el-text-color-primary);

				.title-icon {
					font-size: 18px;
					color: var(--el-color-primary);
				}
			}
		}

		.header-right {
			display: flex;
			align-items: center;
			gap: 8px;
		}
	}

	.messages-flow {
		flex: 1;
		overflow-y: auto;
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 18px;
		background: var(--el-fill-color-extra-light);

		.empty-chat-welcome {
			margin: auto;
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			width: 100%;
			max-width: 680px;
			text-align: center;
			padding: 40px 20px;

			.welcome-avatar {
				width: 56px;
				height: 56px;
				border-radius: 16px;
				background: linear-gradient(135deg, var(--el-color-primary), #a855f7);
				color: #ffffff;
				display: flex;
				align-items: center;
				justify-content: center;
				font-size: 28px;
				margin: 0 auto 16px;
				box-shadow: 0 4px 12px rgba(var(--el-color-primary-rgb), 0.25);
			}

			.welcome-title {
				font-size: 20px;
				font-weight: 600;
				margin: 0 0 8px;
				color: var(--el-text-color-primary);
			}

			.welcome-desc {
				font-size: 13.5px;
				color: var(--el-text-color-secondary);
				margin: 0 0 24px;
				max-width: 520px;
				line-height: 1.5;
			}

			.sample-prompts-grid {
				display: grid;
				grid-template-columns: repeat(2, minmax(240px, 1fr));
				gap: 12px;
				width: 100%;
				text-align: left;

				.sample-card {
					display: flex;
					gap: 10px;
					padding: 12px 14px;
					background: var(--el-bg-color);
					border: 1px solid var(--el-border-color-lighter);
					border-radius: 8px;
					cursor: pointer;
					transition: all 0.2s;

					&:hover {
						border-color: var(--el-color-primary);
						box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
						transform: translateY(-1px);
					}

					.sample-icon {
						font-size: 18px;
						color: var(--el-color-primary);
						margin-top: 2px;
					}

					.sample-content {
						min-width: 0;

						.sample-title {
							font-size: 13px;
							font-weight: 600;
							color: var(--el-text-color-primary);
							margin-bottom: 2px;
						}

						.sample-sub {
							font-size: 11.5px;
							color: var(--el-text-color-secondary);
							overflow: hidden;
							text-overflow: ellipsis;
							white-space: nowrap;
						}
					}
				}
			}
		}
	}
}
</style>
