import { isString } from "lodash-es";
import { getValue, isObject } from ".";

// 解析扩展组件
export function parseExtensionComponent(vnode: Render.Component) {
	if (["el-select", "el-radio-group", "el-checkbox-group"].includes(vnode.name!)) {
		const list = getValue(vnode.options || []);

		const children = (
			<div>
				{list.map((e, i) => {
					let label: any;
					let value: any;

					if (isString(e)) {
						label = value = e;
					} else if (isObject(e)) {
						label = e.label;
						value = e.value;
					} else {
						return <cl-error-message title={`Component options error`} />;
					}

					switch (vnode.name) {
						case "el-select":
							return <el-option key={i} label={label} value={value} {...e.props} />;
						case "el-radio-group":
							return (
								<el-radio key={i} value={value} {...e.props}>
									{label}
								</el-radio>
							);
						case "el-checkbox-group":
							return (
								<el-checkbox key={i} value={value} {...e.props}>
									{label}
								</el-checkbox>
							);
						default:
							return null;
					}
				})}
			</div>
		);

		return {
			children
		};
	} else {
		return {};
	}
}
