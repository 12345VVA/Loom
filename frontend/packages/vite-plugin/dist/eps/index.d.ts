import type { Eps } from "../../types";
/**
 * 主入口：创建 eps 相关文件和 service
 */
export declare function createEps(): Promise<{
    service: {};
    serviceCode: {
        content: string;
        types: string[];
    };
    list: Eps.Entity[];
    isUpdate: boolean;
} | {
    service: {};
    list: never[];
    serviceCode?: undefined;
    isUpdate?: undefined;
}>;
