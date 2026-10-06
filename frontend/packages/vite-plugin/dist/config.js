"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.config = void 0;
exports.config = {
    type: "admin",
    reqUrl: "",
    demo: false,
    nameTag: true,
    eps: {
        enable: true,
        api: "",
        dist: "./build/cool",
        mapping: [
            {
                // 自定义匹配
                custom: ({ propertyName, type }) => {
                    // 如果没有，返回null或者不返回，则继续遍历其他匹配规则
                    return null;
                },
            },
            {
                type: "string",
                test: ["varchar", "text", "simple-json"],
            },
            {
                type: "string[]",
                test: ["simple-array"],
            },
            {
                type: "Date",
                test: ["datetime", "date"],
            },
            {
                type: "number",
                test: ["tinyint", "int", "decimal"],
            },
            {
                type: "BigInt",
                test: ["bigint"],
            },
            {
                type: "any",
                test: ["json"],
            },
            {
                // EPS scanner 的枚举列类型（Python Enum → select）
                type: "string | number",
                test: ["select"],
            },
        ],
    },
    svg: {
        skipNames: ["base"],
    },
    tailwind: {
        enable: true,
        remUnit: 14,
        remPrecision: 6,
        rpxRatio: 2,
        darkTextClass: "dark:text-surface-50",
    },
    uniapp: {
        isPlugin: false,
    },
    clean: false,
    utsPlatform: "web",
};
