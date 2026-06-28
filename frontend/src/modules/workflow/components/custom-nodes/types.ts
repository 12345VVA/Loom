/**
 * 自定义节点多输出 Handle 接口
 * 用于 condition / switch 等分支节点
 */
export interface CustomOutputHandle {
	id: string; // handle id，如 'true'、'false'、'case_0'
	label: string; // 显示标签，如 'T'、'F'
	color?: string; // handle 颜色
	topPercent: number; // 垂直位置百分比
	labelClass?: string; // 标签额外 CSS 类
	handleClass?: string; // handle 额外 CSS 类
}
