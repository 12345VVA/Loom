import { type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getNodeMeta } from '../utils/node-type-registry';
import { buildDefaultConfig } from '../utils/node-default-configs';
import { hitTestGroup } from '../utils/group-hit-test';

interface FlowNode {
	id: string;
	type: string;
	label: string;
	position: { x: number; y: number };
	data: { config: Record<string, any> };
	parentNode?: string;
}

/**
 * 节点工厂 composable（从 editor.vue 抽出）。
 *
 * 收纳节点添加（含 start/end 唯一性、默认 config 构建、loop_body_group 命中归属与自动创建）
 * 及标签、输出变量名的生成工具。默认 config 的数据表见 utils/node-default-configs.ts，
 * 命中判定见 utils/group-hit-test.ts。
 *
 * @param elements 画布元素 ref
 * @param t i18n 翻译函数
 * @param pushSnapshot 撤销快照记录（由 useUndoRedo 提供）
 */
export function useNodeFactory(
	elements: Ref<any[]>,
	t: (k: string) => string,
	pushSnapshot: () => void
) {
	// 取节点类型的本地化显示名（缺失时回落到“未知节点”）
	function getTypeName(type: string) {
		const meta = getNodeMeta(type);
		return t(meta.labelKey || '未知节点');
	}

	// 为新增节点生成不冲突的标签：同类型已有节点时自动追加递增序号
	function getNextLabel(type: string): string {
		const baseName = getTypeName(type);
		const sameTypeNodes = elements.value.filter(
			(el: any) => !('source' in el) && el.type === type
		) as FlowNode[];
		if (sameTypeNodes.length === 0) return baseName;

		let maxNum = 0;
		for (const n of sameTypeNodes) {
			if (n.label === baseName) {
				maxNum = Math.max(maxNum, 1);
			} else {
				const match = n.label.match(new RegExp(`${baseName} (\\d+)$`));
				if (match) {
					maxNum = Math.max(maxNum, parseInt(match[1]));
				}
			}
		}
		return `${baseName} ${maxNum + 1}`;
	}

	// 清洗标签：去空白并剔除非法字符，仅保留字母、数字、下划线与中文，用作变量名前缀
	function sanitizeLabel(label: string): string {
		return label.replace(/\s+/g, '').replace(/[^a-zA-Z0-9_一-鿿]/g, '');
	}

	// 生成全局唯一的输出变量名：以节点标签前缀拼接默认名，遇重名自动追加 _2/_3 后缀
	function getUniqueOutputVar(label: string, defaultVar: string): string {
		const prefix = sanitizeLabel(label);
		const candidate = `${prefix}_${defaultVar}`;
		const existingVars = new Set<string>();
		for (const el of elements.value) {
			if ('source' in el) continue;
			const outVar = (el as FlowNode).data?.config?.outputVariable;
			if (outVar) existingVars.add(outVar);
		}
		if (!existingVars.has(candidate)) return candidate;
		let i = 2;
		while (existingVars.has(`${candidate}_${i}`)) i++;
		return `${candidate}_${i}`;
	}

	/**
	 * 公共添加节点逻辑：唯一性校验 → 生成 id/label/默认 config → group 命中处理 →
	 * loop_controller/batch_processor 自动创建循环体容器 → 记录撤销快照。
	 */
	function handleAddNode(type: string, x: number, y: number) {
		// 开始/结束节点全局唯一，已存在时阻止添加
		if (type === 'start' || type === 'end') {
			const exists = elements.value.some(el => !('source' in el) && el.type === type);
			if (exists) {
				ElMessage.warning(
					t(
						type === 'start'
							? '开始节点已存在，画布中仅允许一个'
							: '结束节点已存在，画布中仅允许一个'
					)
				);
				return;
			}
		}

		const id = `node_${type}_${Date.now()}`;
		const label = getNextLabel(type);
		const config = buildDefaultConfig(type, label, getUniqueOutputVar);

		const newNode: any = {
			id,
			type,
			label,
			position: { x, y },
			data: { config }
		};

		// 检查是否落入 group 中（命中判定见 utils/group-hit-test.ts）
		const hit = hitTestGroup(elements.value, x + 50, y + 20);
		if (hit) {
			// 命中后转为相对 group 的局部坐标，并防止上下边缘溢出（节点默认高约 56px）
			let innerY = y - hit.y;
			if (innerY + 60 > hit.height) innerY = hit.height - 70;
			if (innerY < 40) innerY = 40; // 避开 group-header
			newNode.position.x = x - hit.x;
			newNode.position.y = innerY;
			newNode.parentNode = hit.id;
			newNode.expandParent = true;
		}

		elements.value.push(newNode);

		// 自动创建组容器（不连线，由用户自行从容器 handle 连出）
		if (type === 'loop_controller' || type === 'batch_processor') {
			const groupId = `node_loop_body_group_${Date.now()}`;
			const groupNode = {
				id: groupId,
				type: 'loop_body_group',
				label: type === 'loop_controller' ? `${label} - 循环体` : `${label} - 批处理体`,
				position: { x: x + 250, y: y - 50 },
				style: { width: '400px', height: '250px' },
				data: { config: { controllerNodeId: id } }
			};
			elements.value.push(groupNode);
		}

		// 快照在 group 加入后拍摄，保证 undo 时主节点 + group 原子撤销
		pushSnapshot();
	}

	return { handleAddNode, getNextLabel, getUniqueOutputVar, getTypeName };
}
