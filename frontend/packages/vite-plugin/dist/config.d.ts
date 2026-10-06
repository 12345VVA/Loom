import type { Type } from "../types";
export declare const config: {
    type: Type;
    reqUrl: string;
    demo: boolean;
    nameTag: boolean;
    eps: {
        enable: boolean;
        api: string;
        dist: string;
        mapping: ({
            custom: ({ propertyName, type }: {
                propertyName: string;
                type: string;
            }) => null;
            type?: undefined;
            test?: undefined;
        } | {
            type: string;
            test: string[];
            custom?: undefined;
        })[];
    };
    svg: {
        skipNames: string[];
    };
    tailwind: {
        enable: boolean;
        remUnit: number;
        remPrecision: number;
        rpxRatio: number;
        darkTextClass: string;
    };
    uniapp: {
        isPlugin: boolean;
    };
    clean: boolean;
    utsPlatform: string;
};
