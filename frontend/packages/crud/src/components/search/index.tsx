import { useConfig, useCore, useForm, useProxy, useRefs } from "../../hooks";
import {
	onMounted,
	PropType,
	defineComponent,
	ref,
	h,
	reactive,
	inject,
	mergeProps,
	nextTick,
	onUnmounted
} from "vue";
import { useApi } from "../form/helper";
import { Search, Refresh, Bottom, Top } from "@element-plus/icons-vue";
import { mitt } from "../../utils/mitt";
import { isArray, isEmpty } from "lodash-es";
import { usePlugins } from "./helper/plugins";

export default defineComponent({
	name: "cl-search",

	props: {
		// 是否行内
		inline: {
			type: Boolean,
			default: true
		},

		// cl-form 表单配置
		props: {
			type: Object,
			default: () => ({})
		},

		// 表单值
		data: {
			type: Object,
			default: () => ({})
		},

		// 列
		items: {
			type: Array as PropType<ClForm.Item[]>,
			default: () => []
		},

		// 是否需要重置按钮
		resetBtn: {
			type: Boolean,
			default: false
		},

		// 是否需要折叠
		collapse: {
			type: Boolean,
			default: false
		},

		// 初始化
		onLoad: Function,

		// 搜索时钩子
		onSearch: Function
	},

	emits: ["reset"],

	setup(props, { slots, expose, emit }) {
		const { crud } = useCore();
		const { refs, setRefs } = useRefs()
		const { style } = useConfig();
		const plugin = usePlugins()

		// 配置
		const config = reactive<ClSearch.Config>(
			mergeProps(props, inject("useSearch__options") || {})
		);

		// cl-form
		const Form = useForm();

		// 加载中
		const loading = ref(false);

		// 展开
		const isExpand = ref(!config.collapse);

		// 显示展开、收起按钮
		const showExpandBtn = ref(false);

		// 搜索
		function search(params?: any) {
			const form = Form.value?.getForm();

			async function next(data?: any) {
				loading.value = true;

				const d = {
					page: 1,
					...form,
					...data,
					...params
				};

				for (const i in d) {
					if (d[i] === "") {
						d[i] = undefined;
					}
				}

				const res = await crud.refresh(d);

				loading.value = false;

				return res;
			}

			if (config.onSearch) {
				config.onSearch(form, { next });
			} else {
				next();
			}
		}

		// 重置
		function reset() {
			const d: any = {};

			config.items?.map((e) => {
				if (typeof e.hook != 'string' && e.hook?.reset) {
					const props = e.hook.reset(e.prop!)

					if (isArray(props)) {
						props.forEach((prop) => {
							d[prop] = undefined;
						})
					}
				}

				d[e.prop!] = undefined;
			});

			// 重置表单
			Form.value?.reset();

			// 列表刷新
			search(d);

			// 重置事件
			emit("reset", d);
		}

		// 收起、展开
		function expand() {
			isExpand.value = !isExpand.value;

			nextTick(() => {
				crud?.["cl-table"].calcMaxHeight()
			})
		}

		// 判断展开状态
		function onExpand() {
			if (config.collapse) {
				const el = refs.form?.querySelector(".cl-form__items");

				if (el) {
					showExpandBtn.value = el.clientHeight > 84;
				}
			}
		}

		function onResize() {
			onExpand();
		}

		const ctx = {
			search,
			reset,
			Form,
			config,
			...useApi({ Form })
		};

		useProxy(ctx);
		expose(ctx);
		plugin.create(config.plugins);

		onMounted(() => {
			Form.value?.open({
				op: {
					hidden: true
				},
				props: {
					labelPosition: 'right',
					...config.props
				},
				items: config.items?.map(e => {
					return {
						col: {
							sm: 12,
							md: 8,
							xs: 24,
							lg: 6,
						},
						...e,
					}
				}),
				form: config.data,
				on: {
					open(data) {
						config.onLoad?.(data);
						onExpand();
					},
					change(data, prop) {
						config.onChange?.(data, prop);
					}
				}
			});

			mitt.on("resize", onResize);
		});

		onUnmounted(() => {
			mitt.off("resize", onResize);
		})

		return () => {
			const btnEl = (
				<el-form-item label=" " class="cl-search__btns">
					{/* 重置按钮 */}
					{config.resetBtn && (
						<el-button size={style.size} icon={Refresh} onClick={reset}>
							{crud.dict.label.reset}
						</el-button>
					)}

					{/* 搜索按钮 */}
					<el-button
						type="primary"
						loading={loading.value}
						size={style.size}
						icon={Search}
						onClick={() => {
							search();
						}}>
						{crud.dict.label.search}
					</el-button>

					{/* 自定义按钮 */}
					{slots?.buttons?.(Form.value?.form)}
				</el-form-item>
			);

			return (
				<div class={["cl-search", isExpand.value ? "is-expand" : "is-fold", {
					'is-inline': config.inline,
					'is-collapse': config.collapse,
				}]}>
					<div class="cl-search__form" ref={setRefs("form")}>
						{h(
							<cl-form
								ref={Form}
								inner
								inline={config.inline}
								enable-plugin={false}
								name='search'
							/>,
							{},
							{
								append() {
									return config.collapse ? null : (isEmpty(config.items) || btnEl);
								},
								...slots
							}
						)}
					</div>

					{config.collapse && (
						<div class="cl-search__more">
							{showExpandBtn.value && (
								<el-button onClick={expand}>
									<span>{isExpand.value ? crud.dict.label.collapse : crud.dict.label.expand}</span>
									<el-icon>{isExpand.value ? <Top /> : <Bottom />}</el-icon>
								</el-button>
							)}

							<cl-flex1 />

							{btnEl}
						</div>
					)}
				</div>
			);
		};
	}
});
