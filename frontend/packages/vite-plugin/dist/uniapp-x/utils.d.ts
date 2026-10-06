/**
 * 获取动态类名
 */
export declare const getDynamicClassNames: (value: string) => string[];
/**
 * 获取类名
 */
export declare function getClassNames(code: string): string[];
/**
 * 获取 class 内容
 */
export declare function getClassContent(code: string): string[];
/**
 * 获取节点
 */
export declare function getNodes(code: string): string[];
/**
 * 添加 script 标签内容
 */
export declare function addScriptContent(code: string, content: string): string;
/**
 * 判断是否为 Tailwind 类名
 */
export declare function isTailwindClass(className: string): boolean;
/**
 * 将 interface 转换为 type
 */
export declare function interfaceToType(code: string): string;
