import { type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import type { Connection } from '@vue-flow/core';
import { getEdgeLabel } from '../utils/edge-label';
import type { FlowNode } from '../types/editor';

/**
 * 画布连线 composable（从 editor.vue 抽出）。
 *
 * 收纳 onConnect 的全部校验链（自身/端点约束、分支 Handle 唯一目标、跨容器禁止、去重）、
 * condition 路由写回、边标签推导与边对象生成。边标签推导见 utils/edge-label.ts。
 *
 * @param elements 画布元素 ref
 * @param t i18n 翻译函数
 * @param pushSnapshot 撤销快照记录
 */
export function useEdgeConnect(
	elements: Ref<any[]>,
	t: (k: string) => string,
	pushSnapshot: () => void
) {
	function onConnect(params: Connection) {
		const source = params.source || '';
		const target = params.target || '';
		const sourceHandle = params.sourceHandle;

		// 查找源节点
		const srcNode = elements.value.find((el: any) => !('source' in el) && el.id === source) as
			| FlowNode
			| undefined;
		if (!srcNode) return;

		// 连线验证
		if (source === target) {
			ElMessage.warning(t('不能连接自身'));
			return;
		}
		if (srcNode.type === 'end') {
			ElMessage.warning(t('结束节点不能有出边'));
			return;
		}

		const tgtNode = elements.value.find((el: any) => !('source' in el) && el.id === target) as
			| FlowNode
			| undefined;
		if (tgtNode?.type === 'start') {
			ElMessage.warning(t('开始节点不能有入边'));
			return;
		}

		// condition 每个 Handle 只能连一个目标
		if (srcNode.type === 'condition' && sourceHandle) {
			const existing = elements.value.some(
				(el: any) =>
					'source' in el && el.source === source && (el as any).sourceHandle === sourceHandle
			);
			if (existing) {
				ElMessage.warning(t(sourceHandle === 'true' ? 'True 分支已连线' : 'False 分支已连线'));
				return;
			}
		}

		// intent_classifier / switch 每个 Handle 只能连一个目标
		if ((srcNode.type === 'intent_classifier' || srcNode.type === 'switch') && sourceHandle) {
			const existing = elements.value.some(
				(el: any) =>
					'source' in el && el.source === source && (el as any).sourceHandle === sourceHandle
			);
			if (existing) {
				ElMessage.warning(t('该端口已连线'));
				return;
			}
		}

		// 禁止跨组连线（外部节点不能直连内部节点，内部节点也不能直连外部节点）
		if ((srcNode as any).parentNode !== (tgtNode as any).parentNode) {
			ElMessage.warning(t('禁止跨容器连线，内部节点与外部节点须相互独立'));
			return;
		}

		// 去重：同 source + target + sourceHandle 视为重复。
		// 加入 sourceHandle 比较，避免 condition/switch 多分支连同一目标被误拒
		const exists = elements.value.some(
			(el: any) =>
				'source' in el &&
				el.source === source &&
				el.target === target &&
				(el as any).sourceHandle === sourceHandle
		);
		if (exists) return;

		// 写回 condition 路由字段
		if (srcNode.type === 'condition') {
			const cfg = srcNode.data?.config;
			if (cfg) {
				if (sourceHandle === 'true') cfg.trueRoute = target;
				if (sourceHandle === 'false') cfg.falseRoute = target;
			}
		}

		// 推导边标签
		const label = getEdgeLabel(sourceHandle ?? undefined, srcNode);
		const isConditional =
			srcNode.type === 'condition' ||
			srcNode.type === 'switch' ||
			srcNode.type === 'intent_classifier';

		const newEdge: any = {
			id: 'edge_' + source + '_' + target,
			source,
			target,
			sourceHandle,
			animated: !isConditional,
			type: label ? 'label' : 'default',
			data: { label },
			style: { strokeWidth: 2 }
		};
		elements.value.push(newEdge);
		pushSnapshot();
	}

	return { onConnect };
}
