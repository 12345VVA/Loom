import { describe, expect, it, vi } from 'vitest';
import {
	bindNotifyRecipients,
	buildTaskFormItems,
	submitNotifyRecipients,
	type TaskFormScope
} from '/$/task/utils/task-form';

// 恒等翻译：直接回显 key，便于断言
const t = (key: string) => key;
const components = { cronInput: {}, audienceEditor: {} };

function hiddenOf(prop: string) {
	const field = buildTaskFormItems(t, components).find(f => f.prop === prop);
	return (scope: TaskFormScope) => field?.hidden?.({ scope });
}

describe('task task-form', () => {
	it('builds all fields with translated labels and required marks', () => {
		const items = buildTaskFormItems(t, components);
		const props = items.map(f => f.prop);
		expect(props).toEqual([
			'name',
			'taskType',
			'cron',
			'every',
			'service',
			'startDate',
			'remark',
			'notifyEnabled',
			'notifyOnSuccess',
			'notifyOnFailure',
			'notifyOnTimeout',
			'notifyTimeoutMs',
			'notifyTemplateCode',
			'notifyRecipients'
		]);
		expect(items.find(f => f.prop === 'name')?.required).toBe(true);
		expect(items.find(f => f.prop === 'cron')?.component).toMatchObject({
			name: 'cron-input',
			vm: components.cronInput
		});
		expect(items.find(f => f.prop === 'notifyRecipients')?.component).toMatchObject({
			name: 'notification-audience-editor',
			vm: components.audienceEditor
		});
	});

	it('hides cron fields mutually by taskType', () => {
		const cronHidden = hiddenOf('cron');
		const everyHidden = hiddenOf('every');
		const startDateHidden = hiddenOf('startDate');

		expect(cronHidden?.({ taskType: 0 })).toBe(false);
		expect(cronHidden?.({ taskType: 1 })).toBe(true);
		expect(everyHidden?.({ taskType: 0 })).toBe(true);
		expect(everyHidden?.({ taskType: 1 })).toBe(false);
		expect(startDateHidden?.({ taskType: 1 })).toBe(true);
	});

	it('gates notification fields behind notifyEnabled and timeout threshold behind notifyOnTimeout', () => {
		const notifyHidden = hiddenOf('notifyOnSuccess');
		const timeoutHidden = hiddenOf('notifyTimeoutMs');

		expect(notifyHidden?.({ notifyEnabled: false })).toBe(true);
		expect(notifyHidden?.({ notifyEnabled: true })).toBe(false);
		expect(timeoutHidden?.({ notifyEnabled: true, notifyOnTimeout: true })).toBe(false);
		expect(timeoutHidden?.({ notifyEnabled: true, notifyOnTimeout: false })).toBe(true);
		expect(timeoutHidden?.({ notifyEnabled: false, notifyOnTimeout: true })).toBe(true);
	});

	it('converts every between stored milliseconds and form seconds', () => {
		const field = buildTaskFormItems(t, components).find(f => f.prop === 'every');
		expect(field?.hook?.bind(60000)).toBe(60);
		expect(field?.hook?.submit(60)).toBe(60000);
	});

	describe('notifyRecipients hooks', () => {
		it('bind: parses stored json and falls back to allAdmins', () => {
			expect(bindNotifyRecipients('')).toEqual({ allAdmins: true });
			expect(bindNotifyRecipients(undefined)).toEqual({ allAdmins: true });
			expect(bindNotifyRecipients('{"users":[1,2]}')).toEqual({ users: [1, 2] });
			expect(bindNotifyRecipients('not-json{')).toEqual({ allAdmins: true });
			expect(bindNotifyRecipients({ allAdmins: false })).toEqual({ allAdmins: false });
		});

		it('submit: serializes editor value and defaults to allAdmins', () => {
			expect(submitNotifyRecipients({ users: [3] })).toBe('{"users":[3]}');
			expect(submitNotifyRecipients(undefined)).toBe('{"allAdmins":true}');
			expect(submitNotifyRecipients(null)).toBe('{"allAdmins":true}');
		});
	});
});
