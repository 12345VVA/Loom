import type { Eps } from "../../types";
/**
 * 重置远程退避（dev server /__cool_eps 手动刷新时调用——后端中途启动后可立即重试）
 */
export declare function resetEpsRemote(): void;
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
