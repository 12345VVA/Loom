import AiRuntimeModel from './runtime';

// 模块级运行时调用单例：aiapi scope 的运行时接口不在 EPS 中，
// 业务侧统一 import { aiRuntime } 调用，避免 (service.ai as any).runtime 的类型逃逸。
export const aiRuntime = new AiRuntimeModel();
