/**
 * 计划任务新增/编辑表单配置（从 views/list.vue 拆出，纯声明 + 纯 hook 函数）。
 *
 * 隐藏规则：taskType 0=cron / 1=间隔 互斥切换；通知组字段随 notifyEnabled 联动。
 * hook 换算：every 存库毫秒、交互秒；notifyRecipients 存库 JSON 字符串、交互对象。
 */

export interface TaskFormScope {
	taskType?: number;
	notifyEnabled?: boolean;
	notifyOnTimeout?: boolean;
}

export type TranslateFn = (key: string, named?: Record<string, unknown>) => string;

/** notifyRecipients 的 bind：存库值（JSON 串/空）→ 编辑器对象；解析失败兜底全体管理员。 */
export function bindNotifyRecipients(value: unknown): unknown {
	if (!value) {
		return { allAdmins: true };
	}
	if (typeof value === 'string') {
		try {
			return JSON.parse(value);
		} catch {
			return { allAdmins: true };
		}
	}
	return value;
}

/** notifyRecipients 的 submit：编辑器对象 → 存库 JSON 串；空值兜底全体管理员。 */
export function submitNotifyRecipients(value: unknown): string {
	return JSON.stringify(value || { allAdmins: true });
}

export interface TaskFormComponents {
	/** cron 表达式输入组件（cron-input.vue） */
	cronInput: unknown;
	/** 通知接收人编辑器组件（notification 模块 audience-editor.vue） */
	audienceEditor: unknown;
}

export function buildTaskFormItems(t: TranslateFn, components: TaskFormComponents) {
	return [
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
			hidden: ({ scope }: { scope: TaskFormScope }) => scope.taskType == 1,
			component: {
				name: 'cron-input',
				vm: components.cronInput,
				props: {
					placeholder: '* * * * * *'
				}
			},
			required: true
		},
		{
			label: t('间隔(秒)'),
			prop: 'every',
			hidden: ({ scope }: { scope: TaskFormScope }) => scope.taskType == 0,
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
			hidden: ({ scope }: { scope: TaskFormScope }) => scope.taskType == 1,
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
		},
		{
			label: t('通知设置'),
			prop: 'notifyEnabled',
			value: false,
			component: {
				name: 'el-switch'
			}
		},
		{
			label: t('成功通知'),
			prop: 'notifyOnSuccess',
			value: false,
			hidden: ({ scope }: { scope: TaskFormScope }) => !scope.notifyEnabled,
			component: {
				name: 'el-switch'
			}
		},
		{
			label: t('失败通知'),
			prop: 'notifyOnFailure',
			value: true,
			hidden: ({ scope }: { scope: TaskFormScope }) => !scope.notifyEnabled,
			component: {
				name: 'el-switch'
			}
		},
		{
			label: t('超时通知'),
			prop: 'notifyOnTimeout',
			value: false,
			hidden: ({ scope }: { scope: TaskFormScope }) => !scope.notifyEnabled,
			component: {
				name: 'el-switch'
			}
		},
		{
			label: t('超时阈值(ms)'),
			prop: 'notifyTimeoutMs',
			value: 30000,
			hidden: ({ scope }: { scope: TaskFormScope }) => !scope.notifyEnabled || !scope.notifyOnTimeout,
			component: {
				name: 'el-input-number',
				props: {
					min: 1,
					'controls-position': 'right'
				}
			}
		},
		{
			label: t('通知模板'),
			prop: 'notifyTemplateCode',
			hidden: ({ scope }: { scope: TaskFormScope }) => !scope.notifyEnabled,
			component: {
				name: 'el-input',
				props: {
					placeholder: t('为空时使用默认任务通知模板')
				}
			}
		},
		{
			label: t('通知接收人'),
			prop: 'notifyRecipients',
			hidden: ({ scope }: { scope: TaskFormScope }) => !scope.notifyEnabled,
			hook: {
				bind: bindNotifyRecipients,
				submit: submitNotifyRecipients
			},
			component: {
				name: 'notification-audience-editor',
				vm: components.audienceEditor
			}
		}
	];
}
