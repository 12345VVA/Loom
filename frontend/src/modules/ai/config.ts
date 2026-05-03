import { service, type ModuleConfig } from '/@/cool';
import AiRuntimeModel from './service/runtime';

export default (): ModuleConfig => {
	return {
		order: 7,
		onLoad() {
			const aiService = ((service as any).ai ||= {});
			aiService.runtime = {
				model: new AiRuntimeModel()
			};
		}
	};
};
