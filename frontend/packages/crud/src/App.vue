<template>
	<div>
		<div class="title">CRUD DEMO v8</div>

		<cl-crud ref="Crud">
			<div class="search">
				<cl-search ref="Search" />
			</div>

			<cl-row>
				<cl-add-btn />

				<cl-flex1 />

				<cl-search-key
					field="name"
					:field-list="[
						{
							label: '昵称',
							value: 'name'
						},
						{
							label: '手机号',
							value: 'phone'
						}
					]"
					refreshOnInput
				/>
			</cl-row>

			<cl-row>
				<cl-table ref="Table" :auto-height="false"></cl-table>
			</cl-row>

			<cl-row>
				<cl-flex1 />
				<cl-pagination />
			</cl-row>

			<cl-upsert ref="Upsert"></cl-upsert>
			<cl-form ref="Form"></cl-form>
		</cl-crud>
	</div>
</template>

<script setup lang="tsx">
import { useTable, useForm, useUpsert, useCrud, useSearch } from "./hooks";
import { EditPen } from "@element-plus/icons-vue";

interface Data {
	name?: string;
	age?: number;
	[key: string]: any;
}

const Upsert = useUpsert<Data>({
	items: [
		{
			type: "tabs",
			props: {
				labels: [
					{
						label: "基础",
						value: "A",
						icon: EditPen
					},
					{
						label: "高级",
						value: "B"
					}
				]
			}
		},
		{
			group: "A",
			prop: "age",
			label: "年龄",
			component: {
				name: "el-input"
			}
		},
		{
			group: "A",
			prop: "name",
			label: "昵称",
			component: {
				name: "el-input"
			},
			hidden({ scope }) {
				return scope.age < 18;
			}
		},
		{
			group: "B",
			prop: "phone",
			label: "手机",
			component: {
				name: "el-input"
			},
			hidden({ scope }) {
				return scope.age < 18;
			}
		},
		() => {
			return {
				group: "A",
				hidden: Upsert.value?.mode == "add"
			};
		}
	],
	onOpened(data) {
		console.log(data);
		Upsert.value?.setForm("age", "18");
	}
});

const Table = useTable<Data>(
	{
		contextMenu: [
			{
				label: "带图标",
				prefixIcon: EditPen
			},
			{
				label: "多层级",
				children: [
					{
						label: "A",
						children: [
							{
								label: "A-1"
							}
						]
					},
					{
						label: "B"
					}
				]
			}
		],

		columns: [
			{
				label: "姓名",
				prop: "name",
				search: {
					component: {
						name: "el-date-picker"
					}
				}
			},
			{
				label: "手机号",
				prop: "phone",
				search: {
					component: {
						name: "el-date-picker"
					}
				}
			},
			{
				type: "op"
			}
		]
	},
	(table) => {
		console.log(table);
	}
);

const Crud = useCrud(
	{
		service: "test"
	},
	(app) => {
		app.refresh();
	}
);

const Form = useForm<Data>();

const Search = useSearch({
	collapse: true,
	resetBtn: true,
	items: [
		{
			label: "姓名",
			prop: "name",
			component: {
				name: "el-input"
			},
			hook: {
				reset() {
					return [];
				}
			}
		}
	]
});
</script>

<style scoped>
.title {
	text-align: center;
	font-size: 14px;
	font-weight: bold;
}
</style>
