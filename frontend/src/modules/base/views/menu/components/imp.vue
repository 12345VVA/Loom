<template>
	<cl-upload
		type="file"
		:show-file-list="false"
		:auto-upload="false"
		:disabled="loading"
		@upload="onUpload"
	>
		<el-button type="success" :loading="loading">
			<cl-svg name="import" class="mr-[5px]" />
			{{ $t('导入') }}
		</el-button>
	</cl-upload>

	<cl-form ref="Form">
		<template #slot-tips>
			<el-alert type="warning">
				{{ $t('如遇到问题无法导入菜单，请检查文件并尝试重新导入。') }}
			</el-alert>
		</template>
	</cl-form>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'menu-imp'
});

import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useCrud, useForm } from '@cool-vue/crud';
import { orderBy } from 'lodash-es';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const { service } = useCool();
const Form = useForm();
const Crud = useCrud();

const loading = ref(false);

// 导入文件限制
const MAX_FILE_SIZE = 1 * 1024 * 1024; // 1MB
const MAX_NESTING_DEPTH = 10; // 菜单最大嵌套深度

// 字符串类型字段白名单（键为字段名，值为是否必填）
const STRING_FIELDS: Record<string, boolean> = {
	name: true,
	path: false,
	router: false,
	component: false,
	viewPath: false,
	permission: false,
	icon: false
};

// 数值类型字段白名单
const NUMBER_FIELDS = ['type', 'orderNum', 'sortOrder', 'sort_order'];

// 布尔类型字段白名单
const BOOLEAN_FIELDS = ['keepAlive', 'isShow', 'keep_alive', 'is_show'];

// 子菜单字段可能使用的别名
const CHILDREN_KEYS = ['childMenus', 'children', 'child_menus'];

// 校验单个菜单节点，返回错误信息或 null
function validateMenuNode(node: any, depth: number, path: string): string | null {
	if (depth > MAX_NESTING_DEPTH) {
		return t('菜单嵌套深度超过 {max} 层：{path}', { max: MAX_NESTING_DEPTH, path });
	}

	if (typeof node !== 'object' || node === null || Array.isArray(node)) {
		return t('菜单项必须是对象：{path}', { path });
	}

	// 字符串字段校验
	for (const key in STRING_FIELDS) {
		if (node[key] !== undefined && node[key] !== null) {
			if (typeof node[key] !== 'string') {
				return t('{path}.{field} 必须为字符串', { path, field: key });
			}
			if (STRING_FIELDS[key] && !node[key].trim()) {
				return t('{path}.{field} 不能为空', { path, field: key });
			}
		} else if (STRING_FIELDS[key]) {
			return t('{path} 缺少必填字段 {field}', { path, field: key });
		}
	}

	// 字符串内容安全校验：仅在字段非空时执行
	for (const key in STRING_FIELDS) {
		const val = node[key];
		if (typeof val !== 'string' || !val.trim()) continue;

		// 通用：拒绝包含 <script 的值（防 XSS 注入）
		if (/<script/i.test(val)) {
			return t('{path}.{field} 包含不安全的内容', { path, field: key });
		}

		// 路由路径字段：必须以 / 开头，禁止 javascript:/data: 等危险协议
		if (key === 'path' || key === 'router') {
			if (!val.startsWith('/')) {
				return t('{path}.{field} 必须以 / 开头', { path, field: key });
			}
			if (/(javascript|data):/i.test(val)) {
				return t('{path}.{field} 包含不安全的协议', { path, field: key });
			}
		}

		// 组件路径字段：禁止路径穿越（../）与危险协议
		if (key === 'component' || key === 'viewPath') {
			if (val.includes('../')) {
				return t('{path}.{field} 不能包含路径穿越（../）', { path, field: key });
			}
			if (/(javascript|data):/i.test(val)) {
				return t('{path}.{field} 包含不安全的协议', { path, field: key });
			}
		}
	}

	// 数值字段校验
	for (const field of NUMBER_FIELDS) {
		if (node[field] !== undefined && node[field] !== null) {
			if (typeof node[field] !== 'number' || Number.isNaN(node[field])) {
				return t('{path}.{field} 必须为数值', { path, field });
			}
		}
	}

	// 布尔字段校验
	for (const field of BOOLEAN_FIELDS) {
		if (node[field] !== undefined && node[field] !== null) {
			if (typeof node[field] !== 'boolean') {
				return t('{path}.{field} 必须为布尔值', { path, field });
			}
		}
	}

	// 子菜单递归校验
	for (const key of CHILDREN_KEYS) {
		if (node[key] !== undefined && node[key] !== null) {
			if (!Array.isArray(node[key])) {
				return t('{path}.{field} 必须为数组', { path, field: key });
			}
			for (let i = 0; i < node[key].length; i++) {
				const err = validateMenuNode(
					node[key][i],
					depth + 1,
					`${path}.${key}[${i}]`
				);
				if (err) return err;
			}
		}
	}

	return null;
}

// 校验导入数据结构，返回错误信息或 null
function validateMenuData(data: any): string | null {
	if (!Array.isArray(data)) {
		return t('导入数据必须是菜单数组');
	}
	if (data.length === 0) {
		return t('导入数据不能为空');
	}
	for (let i = 0; i < data.length; i++) {
		const err = validateMenuNode(data[i], 1, `[${i}]`);
		if (err) return err;
	}
	return null;
}

function onUpload(_: any, file: File) {
	// 1. 校验文件扩展名
	const fileName = file.name || '';
	if (!fileName.toLowerCase().endsWith('.json')) {
		ElMessage.error(t('仅支持导入 .json 文件'));
		return;
	}

	// 2. 校验文件大小
	if (file.size > MAX_FILE_SIZE) {
		ElMessage.error(t('文件大小超过 {max} 限制', { max: '1MB' }));
		return;
	}

	// 加载状态
	loading.value = true;

	const reader = new FileReader();

	// 加载完成
	reader.onload = (e: ProgressEvent<FileReader>) => {
		loading.value = false;

		try {
			// 解析数据
			const data = JSON.parse(e.target?.result as string);

			// 3-4. 校验数据结构与嵌套深度
			const validateError = validateMenuData(data);
			if (validateError) {
				ElMessage.error(validateError);
				return;
			}

			// 打开表单
			Form.value?.open({
				title: t('菜单导入'),
				height: '400px',
				width: '600px',
				props: {
					labelWidth: '0px'
				},
				op: {
					saveButtonText: t('添加')
				},
				items: [
					{
						component: {
							name: 'slot-tips'
						}
					},
					{
						component: {
							name: 'el-tree',
							props: {
								data: orderBy(data, 'orderNum', 'asc'),
								nodeKey: 'name',
								props: {
									label: 'name',
									children: 'childMenus'
								},
								renderContent(_: any, { data }: any) {
									return data.name;
								}
							},
							style: {
								padding: '5px',
								borderRadius: 'var(--el-border-radius-base)',
								border: '1px solid var(--el-border-color)'
							}
						}
					}
				],
				on: {
					submit(_, { close, done }) {
						service.base.sys.menu
							.import({
								menus: data
							})
							.then(() => {
								ElMessage.success(t('导入成功'));
								Crud.value?.refresh();
								close();
							})
							.catch(err => {
								ElMessage.error(err.message);
								done();
							});
					}
				}
			});
		} catch (error) {
			ElMessage.error(t('{file}文件格式错误：{error}', { file: file.name, error }));
		}
	};

	// 读取文件
	reader.readAsText(file);
}
</script>
