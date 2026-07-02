import { genId } from '../utils';

/**
 * 加载工作流拓扑后的字段迁移/适配（纯函数）。
 *
 * 仅保留两类必需处理：
 * - tool_executor：后端 config 存 `arguments` 对象，编辑器用 `argumentsJson` 字符串编辑，
 *   加载时把对象序列化为字符串供 UI 使用（保存时 useGraphBuilder 反向转换）。
 * - switch.cases / intent_classifier.intents 缺 `id` 时补稳定 id；
 *   id 是分支 sourceHandle 稳定性的基础，缺失会导致端口体系错位。
 *
 * 已删除的旧版本兼容（激进清理，全仓示例数据均已为新格式）：
 * - start/end/llm 默认值补全、sourceHandle 下标(case_N/intent_N)→id、从 config 路由反向重建 sourceHandle。
 */
export function migrateLoadedElements(elements: any[]): any[] {
	for (const el of elements) {
		if ('source' in el) continue; // 仅处理节点，边无 type/config
		adaptToolExecutorForEditor(el);
		ensureStableCaseIntentIds(el);
	}
	return elements;
}

/**
 * tool_executor 编辑态适配：把 config.arguments（对象）序列化为 argumentsJson（字符串）。
 * 已有 argumentsJson 时不覆盖，保证幂等。arguments 字段保留（保存时由 buildGraphPayload 重建）。
 */
function adaptToolExecutorForEditor(el: any) {
	if (el.type !== 'tool_executor') return;
	const conf = el.data?.config;
	if (!conf) return;
	if (conf.arguments && !conf.argumentsJson) {
		conf.argumentsJson = JSON.stringify(conf.arguments, null, 2);
	}
}

/**
 * 为 switch.cases / intent_classifier.intents 缺 id 的条目补稳定 id（幂等）。
 * id 是分支端口（case_<id> / intent_<id>）的锚点，缺失会导致连线 handle 错位。
 */
function ensureStableCaseIntentIds(el: any) {
	const conf = el.data?.config;
	if (!conf) return;
	if (el.type === 'switch' && Array.isArray(conf.cases)) {
		conf.cases.forEach((c: any) => {
			if (!c.id) c.id = genId();
		});
	} else if (el.type === 'intent_classifier' && Array.isArray(conf.intents)) {
		conf.intents.forEach((i: any) => {
			if (!i.id) i.id = genId();
		});
	}
}
