import { toSafeClass } from "./uniapp-x/tailwind";
import { getClassContent, getClassNames, getNodes, isTailwindClass } from "./uniapp-x/utils";

export function test() {
	const html = `
	<template>
		1<text :class="parseClass({'!bg-red-50': hoverable})"></text>
		2<text :class="a ? 'text-red-100' : 'text-red-200'"></text>
		3<text :class="\`text-red-300 \${true ? 'text-red-310' : 'text-red-320'}\`"></text>
		4<text class="text-red-330"></text>
		5<text :class="{
			'text-red-400': a,
			'text-red-500': b,
		}"></text>
		6<text :class="[
			'text-red-600',
			'text-red-700',
			{
				'text-red-800': c,
			}
		]"></text>
		7<text :class="\`text-red-900\` text-red-1000"></text>
		8<text :pt="{
			className: '!text-green-50'
		}"></text>
		9<text :pt="{
			className: parseClass({
				'!text-green-100': hoverable,
			}),
			item: {
				className: '!text-green-200'
			},
			title: {
				className: '!text-green-300'
			}
		}"></text>
		10<text :pt="{
			className: \`text-green-300 \${true ? 'text-red-310' : 'text-red-320'}\`
		}"></text>
		11<text hover-class="text-green-400"></text>
		12<text :hover-class="\`text-green-400\`"></text>
		13<text :hover-class="parseClass({'!text-green-450': hoverable})"></text>
		14<text :hover-class="a ? 'text-green-500' : 'text-green-600'"></text>
		15<text :hover-class="\`text-green-700 \${true ? 'text-red-310' : 'text-red-320'}\`"></text>
		16<cl-timeline-item
			icon="checkbox-circle-fill"
			:pt="{
				title: {
					className: '!text-primary-500'
				},
				icon: {
					className: '!text-primary-400'
				}
			}"
			title="更快速"
			date="2025-06-28 10:00:00"
			content="通过集成 cool-admin 的用户登录、版本管理、消息通知以及订单管理等基础模块。有效降低了开发成本，进而增强了市场竞争力。"
		>
		</cl-timeline-item>
		17<text class="title dark:!text-surface-50"></text>
	</template>
`;

	const nodes = getNodes(html);

	console.log("所有节点:");
	nodes.forEach((node, index) => {
		console.log(`第${index + 1}个节点:`, node);
	});

	console.log("\n详细分析:");
	nodes.forEach((node, index) => {
		const classContents = getClassContent(node);
		const classNames = getClassNames(node);
		console.log(`第${index + 1}个节点:`);
		console.log("classContents", classContents);
		console.log("classNames", classNames);

		classNames.forEach((className) => {
			console.log("safeClass", toSafeClass(className));
		});
		console.log("---");
	});

	console.log(isTailwindClass("dark:!text-surface-50"));
}

test();

// npx tsx src/test.ts
