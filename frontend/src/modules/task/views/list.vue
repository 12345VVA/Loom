<template>
	<div class="task-list" :class="{ 'is-mini': browser.isMini }">
		<div class="list">
			<div
				v-for="item in list"
				:key="item.id"
				class="item"
				:class="{ 'is-active': item.status }"
				@click="edit(item)"
				@contextmenu="(e) => onContextMenu(e, item)"
			>
				<div class="header">
					<p class="name">{{ item.name }}</p>
					<div
						class="status-indicator"
						:class="item.status ? 'is-running' : 'is-stopped'"
					>
						<span class="dot"></span>
						{{ item.status ? $t('运行中') : $t('已停止') }}
					</div>
				</div>

				<div class="content">
					<div class="row">
						<span class="label">{{ $t('执行服务') }}</span>
						<span class="value">{{ item.service }}</span>
					</div>
					<div class="row">
						<span class="label">{{ $t('规则') }}</span>
						<span class="value">
							{{
								item.taskType == 1
									? $t('每隔{n}s', { n: item._every })
									: item.cron
							}}
						</span>
					</div>
				</div>

				<div class="footer">
					<div class="actions">
						<el-tooltip :content="item.status ? $t('暂停') : $t('启动')" placement="top">
							<el-icon
								v-permission="
									item.status
										? service.task.info.permission.stop
										: service.task.info.permission.start
								"
								:class="item.status ? 'pause-btn' : 'play-btn'"
								@click.stop="item.status ? stop(item) : start(item)"
							>
								<VideoPause v-if="item.status" />
								<VideoPlay v-else />
							</el-icon>
						</el-tooltip>
					</div>

					<cl-flex1 />

					<div class="ops">
						<el-tooltip :content="$t('立即执行')" placement="top">
							<el-icon
								class="run-btn"
								@click.stop="once(item)"
								v-permission="service.task.info.permission.once"
							>
								<CaretRight />
							</el-icon>
						</el-tooltip>

						<el-tooltip :content="$t('日志')" placement="top">
							<el-icon
								class="log-btn"
								@click.stop="log(item)"
								v-permission="service.task.info.permission.log"
							>
								<Tickets />
							</el-icon>
						</el-tooltip>

						<el-tooltip :content="$t('删除')" placement="top">
							<el-icon
								class="delete-btn"
								@click.stop="remove(item)"
								v-permission="service.task.info.permission.delete"
							>
								<Delete />
							</el-icon>
						</el-tooltip>
					</div>
				</div>
			</div>

			<div
				class="item is-add"
				@click="edit()"
				v-permission="service.task.info.permission.add"
			>
				<div class="add-inner">
					<el-icon><Plus /></el-icon>
					<p>{{ $t('新建计划任务') }}</p>
				</div>
			</div>
		</div>

		<!-- 表单 -->
		<cl-form ref="Form" />

		<!-- 日志 -->
		<task-logs :ref="setRefs('log')" />
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'task-list'
});

import { onActivated, ref, markRaw } from 'vue';
import { useBrowser, useCool } from '/@/cool';
import { VideoPlay, VideoPause, Plus, Tickets, Delete, CaretRight } from '@element-plus/icons-vue';
import { ContextMenu, useForm } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import TaskLogs from '../components/logs.vue';
import CronInput from '../components/cron-input.vue';
import { useI18n } from 'vue-i18n';

const { service, refs, setRefs } = useCool();
const { browser } = useBrowser();
const Form = useForm();
const { t } = useI18n();

const list = ref<Eps.TaskInfoEntity[]>([]);

// 刷新
function refresh() {
	service.task.info.page({ size: 100, page: 1 }).then(res => {
		list.value = res.list.map(e => {
			if (e.every) {
				e._every = parseInt(String(e.every / 1000));
			}

			return e;
		});
	});
}

// 统一操作处理器
async function handleAction(item: Eps.TaskInfoEntity, actionName: string, run: () => Promise<any>) {
	try {
		await ElMessageBox.confirm(t('此操作将{action}任务（{name}），是否继续？', { action: actionName, name: item.name }), t('提示'), {
			type: 'warning'
		});
		await run();
		ElMessage.success(t('{action}成功', { action: actionName }));
		refresh();
	} catch (err: any) {
		if (err !== 'cancel') {
			ElMessage.error(err.message || t('操作失败'));
		}
	}
}

// 启用任务
function start(item: Eps.TaskInfoEntity) {
	console.log(t('启用任务'), item);
	handleAction(item, t('启用'), () => service.task.info.start({ id: item.id, type: item.type }));
}

// 停用任务
function stop(item: Eps.TaskInfoEntity) {
	console.log(t('停止任务'), item);
	handleAction(item, t('停用'), () => service.task.info.stop({ id: item.id }));
}

// 删除任务
function remove(item: Eps.TaskInfoEntity) {
	handleAction(item, t('删除'), () => service.task.info.delete({ ids: [item.id] }));
}

// 任务日志
function log(item: Eps.TaskInfoEntity) {
	refs.log.open(item);
}

// 表单配置
const items: any[] = [
	{
		label: t('名称'),
		prop: 'name',
		component: {
			name: 'el-input',
			props: {
				placeholder: t('请输入名称')
			}
		},
		required: true
	},
	{
		label: t('类型'),
		prop: 'taskType',
		value: 0,
		component: {
			name: 'el-radio-group',
			options: [
				{
					label: 'cron',
					value: 0
				},
				{
					label: t('时间间隔'),
					value: 1
				}
			]
		},
		required: true
	},
	{
		label: 'cron',
		prop: 'cron',
		hidden: ({ scope }: any) => scope.taskType == 1,
		component: {
			name: 'cron-input',
			vm: markRaw(CronInput),
			props: {
				placeholder: '* * * * * *'
			}
		},
		required: true
	},
	{
		label: t('间隔(秒)'),
		prop: 'every',
		hidden: ({ scope }: any) => scope.taskType == 0,
		hook: {
			bind(value: number) {
				return value / 1000;
			},
			submit(value: number) {
				return value * 1000;
			}
		},
		component: {
			name: 'el-input-number',
			props: {
				min: 1,
				max: 100000000
			}
		},
		required: true
	},
	{
		label: 'service',
		prop: 'service',
		component: {
			name: 'el-input',
			props: {
				placeholder: 'taskDemoService.test([1, 2])'
			}
		}
	},
	{
		label: t('开始时间'),
		prop: 'startDate',
		hidden: ({ scope }: any) => scope.taskType == 1,
		component: {
			name: 'el-date-picker',
			props: {
				type: 'datetime',
				'value-format': 'YYYY-MM-DD HH:mm:ss'
			}
		}
	},
	{
		label: t('备注'),
		prop: 'remark',
		component: {
			name: 'el-input',
			props: {
				type: 'textarea',
				rows: 3
			}
		}
	}
];

// 新增、编辑
async function edit(item?: Eps.TaskInfoEntity) {
	if (item && !service.task.info._permission.update) {
		return false;
	}

	Form.value?.open({
		title: t('编辑计划任务'),
		width: '600px',
		props: {
			labelWidth: '80px'
		},
		items,
		form: {
			...item
		},
		on: {
			submit: (data, { close, done }) => {
				if (!data.limit) {
					data.limit = null;
				}

				service.task.info[item?.id ? 'update' : 'add'](data)
					.then(() => {
						refresh();
						ElMessage.success(t('保存成功'));
						close();
					})
					.catch(err => {
						ElMessage.error(err.message);
						done();
					});
			}
		}
	});
}

// 执行一次
function once(item: Eps.TaskInfoEntity) {
	service.task.info
		.once({ id: item.id })
		.then(() => {
			refresh();
		})
		.catch(err => {
			ElMessage.error(err.message);
		});
}

// 右键菜单
function onContextMenu(e: any, item: Eps.TaskInfoEntity) {
	ContextMenu.open(e, {
		list: [
			item.status
				? {
						label: t('暂停'),
						hidden: !service.task.info._permission.stop,
						callback(done) {
							stop(item);
							done();
						}
				  }
				: {
						label: t('开始'),
						hidden: !service.task.info._permission.start,
						callback(done) {
							start(item);
							done();
						}
				  },
			{
				label: t('立即执行'),
				hidden: !service.task.info._permission.once,
				callback(done) {
					once(item);
					done();
				}
			},
			{
				label: t('编辑'),
				hidden: !(
					service.task.info._permission.update && service.task.info._permission.info
				),
				callback(done) {
					edit(item);
					done();
				}
			},
			{
				label: t('删除'),
				hidden: !service.task.info._permission.delete,
				callback(done) {
					remove(item);
					done();
				}
			},
			{
				label: t('查看日志'),
				hidden: !service.task.info._permission.log,
				callback(done) {
					log(item);
					done();
				}
			}
		]
	});
}

onActivated(() => {
	refresh();
});
</script>

<style lang="scss" scoped>
.task-list {
	height: 100%;
	overflow-y: auto;
	padding: 20px;
	box-sizing: border-box;
	background-color: var(--el-bg-color-page);

	.list {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 20px;
		background-color: inherit;

		.item {
			background-color: var(--el-bg-color);
			border-radius: 12px;
			padding: 20px;
			height: 220px;
			display: flex;
			flex-direction: column;
			position: relative;
			transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
			border: 1px solid var(--el-border-color-lighter);
			cursor: pointer;
			box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);

			&:hover {
				transform: translateY(-5px);
				box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
				border-color: var(--el-color-primary-light-5);
			}

			&.is-active {
				border-color: var(--el-color-success-light-5);
				background: linear-gradient(
					to bottom right,
					var(--el-bg-color),
					var(--el-color-success-light-9)
				);
			}

			.header {
				display: flex;
				justify-content: space-between;
				align-items: flex-start;
				margin-bottom: 20px;

				.name {
					font-size: 18px;
					font-weight: 600;
					color: var(--el-text-color-primary);
					margin: 0;
					flex: 1;
					overflow: hidden;
					white-space: nowrap;
					text-overflow: ellipsis;
					margin-right: 12px;
				}

				.status-indicator {
					display: flex;
					align-items: center;
					font-size: 12px;
					padding: 4px 12px;
					border-radius: 20px;
					font-weight: 600;
					transition: all 0.3s;
					user-select: none;

					.dot {
						width: 8px;
						height: 8px;
						border-radius: 50%;
						margin-right: 6px;
					}

					&.is-running {
						background-color: var(--el-color-success-light-9);
						color: var(--el-color-success);
						border: 1px solid var(--el-color-success-light-8);
						.dot {
							background-color: var(--el-color-success);
							box-shadow: 0 0 6px var(--el-color-success);
							animation: blink 2s infinite;
						}
						&:hover {
							background-color: var(--el-color-success-light-8);
						}
					}

					&.is-stopped {
						background-color: var(--el-color-info-light-9);
						color: var(--el-color-info);
						border: 1px solid var(--el-color-info-light-8);
						.dot {
							background-color: var(--el-color-info);
						}
						&:hover {
							background-color: var(--el-color-info-light-8);
						}
					}
				}
			}

			.content {
				flex: 1;
				.row {
					margin-bottom: 12px;
					.label {
						font-size: 12px;
						color: var(--el-text-color-secondary);
						display: block;
						margin-bottom: 4px;
					}
					.value {
						font-size: 14px;
						color: var(--el-text-color-regular);
						font-family: var(--el-font-family-mono, 'Roboto Mono', monospace);
						word-break: break-all;
						display: -webkit-box;
						-webkit-box-orient: vertical;
						-webkit-line-clamp: 1;
						line-clamp: 1;
						overflow: hidden;
					}
				}
			}

			.footer {
				margin-top: 15px;
				padding-top: 15px;
				border-top: 1px solid var(--el-border-color-extra-light);
				display: flex;
				align-items: center;

				.el-icon {
					font-size: 20px;
					padding: 6px;
					border-radius: 8px;
					transition: all 0.2s;
					margin-right: 8px;

					&:hover {
						background-color: var(--el-fill-color-light);
					}

					&.play-btn {
						color: var(--el-color-primary);
						&:hover {
							background-color: var(--el-color-primary-light-9);
						}
					}

					&.pause-btn {
						color: var(--el-color-danger);
						&:hover {
							background-color: var(--el-color-danger-light-9);
						}
					}

					&.run-btn {
						color: var(--el-color-primary);
						&:hover {
							background-color: var(--el-color-primary-light-9);
						}
					}

					&.log-btn {
						color: var(--el-color-warning);
						&:hover {
							background-color: var(--el-color-warning-light-9);
						}
					}

					&.delete-btn {
						color: var(--el-color-info);
						&:hover {
							color: var(--el-color-danger);
							background-color: var(--el-color-danger-light-9);
						}
					}
				}
			}

			&.is-add {
				border: 2px dashed var(--el-border-color-darker);
				background-color: transparent;
				justify-content: center;
				align-items: center;
				color: var(--el-text-color-secondary);

				&:hover {
					border-color: var(--el-color-primary);
					color: var(--el-color-primary);
					background-color: var(--el-color-primary-light-9);
				}

				.add-inner {
					text-align: center;
					.el-icon {
						font-size: 40px;
						margin-bottom: 10px;
					}
					p {
						font-size: 15px;
						font-weight: 500;
					}
				}
			}
		}
	}

	&.is-mini {
		padding: 10px;
		.list {
			grid-template-columns: 100%;
		}
	}
}

@keyframes blink {
	0% {
		opacity: 1;
		transform: scale(1);
	}
	50% {
		opacity: 0.5;
		transform: scale(1.2);
	}
	100% {
		opacity: 1;
		transform: scale(1);
	}
}
</style>
