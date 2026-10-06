import prettier from "prettier";
export declare function rootDir(path: string): string;
export declare function firstUpperCase(value: string): string;
export declare function toCamel(str: string): string;
export declare function createDir(path: string, recursive?: boolean): void;
export declare function readFile(path: string, json?: boolean): any;
export declare function writeFile(path: string, data: any): void | "";
export declare function parseJson(req: any): Promise<any>;
export declare function formatContent(content: string, options?: prettier.Options): Promise<string>;
export declare function error(message: string): void;
export declare function success(message: string): void;
/**
 * 比较两个版本号
 * @param version1 版本号1 (如: "1.2.3")
 * @param version2 版本号2 (如: "1.2.4")
 * @returns 1: version1 > version2, 0: 相等, -1: version1 < version2
 */
export declare function compareVersion(version1: string, version2: string): number;
