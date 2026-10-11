/**
 * 试运行 / 单节点测试弹窗的可视化表单（WFI-1c 多模态一期）。
 *
 * 按 start 节点（或单节点测试的上游变量）声明渲染控件：
 * - image → 上传控件（经媒体库 /upload 换取 /uploads 相对 URL）+ URL 手输二合一；
 * - number → 数字输入；boolean → 开关；string → 文本域。
 * 与 JSON 模式（cl-editor-codemirror）双向同步；提交前校验 required 与
 * data: 前缀本地拦截（后端 _reject_inline_data_uris 为权威防线，此处是体验层）。
 */

import { computed, ref } from 'vue';
import { ElMessage } from 'element-plus';

import { buildStartInputsTemplate, type StartInputVariableType } from '../utils/start-inputs';

export interface TestFormVariable {
	name: string;
	type: StartInputVariableType;
	required?: boolean;
}

export function useTestForm(service: any, t: any) {
	const mode = ref<'form' | 'json'>('form');
	const values = ref<Record<string, unknown>>({});
	const declared = ref<TestFormVariable[]>([]);
	const uploadingKey = ref('');

	/** 声明了变量才提供表单模式；否则仅 JSON 模式（与旧行为一致） */
	const formAvailable = computed(() => declared.value.length > 0);

	function switchMode(target: 'form' | 'json') {
		mode.value = target;
	}

	/**
	 * 按声明初始化表单。
	 * @param vars 变量声明（含类型）
	 * @param rawStartConfig start 节点 config（用于默认值模板；单节点测试传 null）
	 * @param initial 已有值（如上次缓存），缺省键按类型补初值
	 */
	function initFromVariables(vars: TestFormVariable[], rawStartConfig: unknown, initial?: Record<string, unknown>) {
		declared.value = vars;
		const defaults = rawStartConfig ? buildStartInputsTemplate(rawStartConfig) : {};
		values.value = { ...defaults };
		for (const v of vars) {
			if (initial && v.name in initial) {
				values.value[v.name] = initial[v.name];
			} else if (!(v.name in values.value) || values.value[v.name] === undefined) {
				values.value[v.name] = v.type === 'number' ? 0 : v.type === 'boolean' ? false : '';
			}
		}
		mode.value = 'form';
	}

	/** 表单值 → JSON 文本（切 JSON 模式 / 缓存场景） */
	function toJson(): string {
		return JSON.stringify(values.value, null, 2);
	}

	/** JSON 文本 → 表单值；解析失败返回 false（调用方锁定表单模式或提示） */
	function fromJson(json: string): boolean {
		try {
			const parsed = JSON.parse(json);
			if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
				values.value = parsed;
				return true;
			}
			return false;
		} catch {
			return false;
		}
	}

	/** 上传图片并回填相对 URL（URL 介质原则：值始终是字符串 URL） */
	async function uploadImage(key: string, file: File) {
		uploadingKey.value = key;
		try {
			const form = new FormData();
			form.append('file', file);
			const res = await service.media.asset.request({
				url: '/upload',
				method: 'POST',
				data: form
			});
			if (res?.url) {
				values.value[key] = res.url;
			} else {
				ElMessage.error(t('上传成功但未返回地址'));
			}
		} catch (err: any) {
			ElMessage.error(t('图片上传失败: ') + (err?.message || err));
		} finally {
			uploadingKey.value = '';
		}
	}

	/** 提交前校验：返回首个不合规描述，合规返回 null */
	function validate(): string | null {
		for (const v of declared.value) {
			const val = values.value[v.name];
			if (v.required && (val === '' || val === undefined || val === null)) {
				return t('变量 {name} 为必填项').replace('{name}', v.name);
			}
			const items = Array.isArray(val) ? val : [val];
			for (const item of items) {
				if (typeof item === 'string' && item.startsWith('data:')) {
					return t('变量 {name} 不支持直接粘贴 Base64，请上传图片后使用 URL').replace('{name}', v.name);
				}
			}
		}
		return null;
	}

	/** 表单模式取提交用 inputs（校验失败返回 null 并提示） */
	function getInputs(): Record<string, unknown> | null {
		const problem = validate();
		if (problem) {
			ElMessage.warning(problem);
			return null;
		}
		return { ...values.value };
	}

	return {
		mode,
		values,
		declared,
		uploadingKey,
		formAvailable,
		switchMode,
		initFromVariables,
		toJson,
		fromJson,
		uploadImage,
		validate,
		getInputs
	};
}
