import { service, type ModuleConfig } from '/@/cool';
import { aiRuntime } from './index';

export default (): ModuleConfig => {
	return {
		order: 7,
		onLoad() {
			// 兼容既有 (service.ai as any).runtime.model 调用形态；新代码请直接 import { aiRuntime }
			const aiService = ((service as any).ai ||= {});
			aiService.runtime = {
				model: aiRuntime
			};
		}
	};
};
