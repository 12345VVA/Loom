import AiRuntimeModel from './service/runtime';

// 模块级运行时调用单例：aiapi scope 的运行时接口不在 EPS 中，
// 业务侧统一 import { aiRuntime } from '/$/ai' 调用，避免 (service.ai as any).runtime 的类型逃逸。
// 注意：不能放在 service/ 目录下——bootstrap/module.ts 以 import: 'default' 扫描 service/**，
// 无默认导出的文件会在运行时报 SyntaxError。
export const aiRuntime = new AiRuntimeModel();
