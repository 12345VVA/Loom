// workflow_eval 模块的纯格式化/解析工具函数。
// 从 views/compare.vue 与 views/run.vue 中抽离，便于单元测试与复用。
// 注意：本文件不依赖 vue-i18n / element-plus 运行时，仅做纯数据映射与 JSON 解析。

/**
 * 评估对比 verdict 对应的 element-plus tag 类型。
 * - regression（显著退化）→ error
 * - improvement（显著改善）→ success
 * - insignificant（无显著变化）→ info
 * - insufficient_sample（样本不足）→ warning
 * - 未知值兜底 → info
 *
 * 返回 any 以兼容 element-plus tag `type` 属性的联合类型（与原 vue 内联实现一致）。
 */
export function verdictType(v: string): any {
	return (
		{
			regression: 'error',
			improvement: 'success',
			insignificant: 'info',
			insufficient_sample: 'warning'
		} as Record<string, string>
	)[v] || 'info';
}

/**
 * 评估运行状态对应的 element-plus tag 类型。
 * - succeeded → success
 * - failed → danger
 * - running → warning
 * - cancelled → info
 * - partial → warning
 * - pending → info
 * - 未知值兜底 → ''
 *
 * 返回 any 以兼容 element-plus tag `type` 属性的联合类型（与原 vue 内联实现一致）。
 */
export function statusTagType(s: string): any {
	return (
		{
			succeeded: 'success',
			failed: 'danger',
			running: 'warning',
			cancelled: 'info',
			partial: 'warning',
			pending: 'info'
		} as Record<string, string>
	)[s] || '';
}

/**
 * 评估用例执行状态对应的 element-plus tag 类型。
 * - success → success
 * - fail / error → danger
 * - timeout → warning
 * - blocked → info
 * - 未知值兜底 → ''
 *
 * 返回 any 以兼容 element-plus tag `type` 属性的联合类型（与原 vue 内联实现一致）。
 */
export function caseStatusType(s: string): any {
	return (
		{
			success: 'success',
			fail: 'danger',
			error: 'danger',
			timeout: 'warning',
			blocked: 'info'
		} as Record<string, string>
	)[s] || '';
}

/**
 * judge 校准 κ 水平对应的 element-plus tag 类型。
 * - reliable（≥0.6）→ success
 * - moderate（0.4-0.6）→ warning
 * - unreliable（<0.4）→ danger
 * - no_annotation（无标注）→ info
 * - 未知值兜底 → info
 *
 * 返回 any 以兼容 element-plus tag `type` 属性的联合类型（与原 vue 内联实现一致）。
 */
export function kappaLevelType(level: string): any {
	return (
		{
			reliable: 'success',
			moderate: 'warning',
			unreliable: 'danger',
			no_annotation: 'info'
		} as Record<string, string>
	)[level] || 'info';
}

/**
 * 解析 evaluator_detail 字段：兼容 string（JSON）与 object 两种存储形式。
 * 入参为空返回 null；解析失败返回 null（不抛错，供展开行兜底渲染）。
 */
export function parseJudgeDetail(s: any): any {
	if (!s) return null;
	try {
		return typeof s === 'string' ? JSON.parse(s) : s;
	} catch {
		return null;
	}
}
