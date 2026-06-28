import {
	VideoPlay,
	CircleClose,
	ChatDotRound,
	Operation,
	Share,
	Avatar,
	Connection,
	Refresh,
	CopyDocument,
	Picture,
	MagicStick,
	Collection,
	Filter,
	InfoFilled
} from '@element-plus/icons-vue';

// 统一管理所有节点类型的元数据
export const NODE_REGISTRY = [
	{
		type: 'start',
		labelKey: '开始',
		icon: VideoPlay,
		colorClass: 'node-start',
		colorHex: '#67c23a'
	},
	{
		type: 'end',
		labelKey: '结束',
		icon: CircleClose,
		colorClass: 'node-end',
		colorHex: '#f56c6c'
	},
	{
		type: 'llm',
		labelKey: 'LLM 节点',
		icon: ChatDotRound,
		colorClass: 'node-llm',
		colorHex: '#409eff',
		category: 'ai',
		descKey: '调用大语言模型进行文本处理与生成'
	},
	{
		type: 'image_generator',
		labelKey: '生图节点',
		icon: Picture,
		colorClass: 'node-image_generator',
		colorHex: '#ff69b4',
		category: 'ai',
		descKey: '调用大模型生成图片'
	},
	{
		type: 'intent_classifier',
		labelKey: '意图分类',
		icon: Connection,
		colorClass: 'node-intent_classifier',
		colorHex: '#20b2aa',
		category: 'ai',
		descKey: '基于大模型的文本意图判断'
	},
	{
		type: 'tool_executor',
		labelKey: '工具执行器',
		icon: MagicStick,
		colorClass: 'node-tool_executor',
		colorHex: '#e6a23c',
		category: 'system',
		descKey: '执行外部工具、API 或自定义代码'
	},
	{
		type: 'condition',
		labelKey: '条件分支',
		icon: Operation,
		colorClass: 'node-condition',
		colorHex: '#e6a23c',
		category: 'logic',
		descKey: '根据条件表达式分流执行路径'
	},
	{
		type: 'switch',
		labelKey: '分支选择',
		icon: Share,
		colorClass: 'node-switch',
		colorHex: '#e6a23c',
		category: 'logic',
		descKey: '根据变量值选择多条执行路径之一'
	},
	{
		type: 'loop_controller',
		labelKey: '循环控制',
		icon: Refresh,
		colorClass: 'node-loop_controller',
		colorHex: '#d2691e',
		category: 'logic',
		descKey: '循环执行内部节点群'
	},
	{
		type: 'batch_processor',
		labelKey: '并发批处理',
		icon: CopyDocument,
		colorClass: 'node-batch_processor',
		colorHex: '#00ced1',
		category: 'logic',
		descKey: '并发执行多组数据'
	},
	{
		type: 'human_input',
		labelKey: '人工审批',
		icon: Avatar,
		colorClass: 'node-human_input',
		colorHex: '#909399',
		category: 'system',
		descKey: '中断工作流，等待人工输入或审批'
	},
	{
		type: 'variable_assignment',
		labelKey: '变量设置',
		icon: Collection,
		colorClass: 'node-variable_assignment',
		colorHex: '#409eff',
		category: 'system',
		descKey: '设置全局/局部变量'
	},
	{
		type: 'variable_transform',
		labelKey: '数据转换',
		icon: Filter,
		colorClass: 'node-variable_transform',
		colorHex: '#67c23a',
		category: 'system',
		descKey: '格式转换与数据提取'
	},
	{
		type: 'tool',
		labelKey: '工具执行',
		icon: MagicStick,
		colorClass: 'node-tool',
		colorHex: '#e6a23c',
		category: 'system',
		descKey: '旧版工具节点',
		deprecated: true
	},
	{
		type: 'loop_body_group',
		labelKey: '循环体',
		icon: Refresh,
		colorClass: 'node-loop_body_group',
		colorHex: '#d2691e',
		category: 'logic',
		descKey: '循环内部组件块'
	}
];

export function getNodeMeta(type: string) {
	return NODE_REGISTRY.find(n => n.type === type) || {
		type,
		labelKey: '未知节点',
		icon: InfoFilled,
		colorClass: 'node-unknown',
		colorHex: '#909399'
	};
}
