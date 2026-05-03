import { BaseService } from '/@/cool';

class AiRuntimeModel extends BaseService {
	constructor() {
		super('aiapi/ai/model');
	}

	chat(data: any) {
		return this.request({
			url: '/chat',
			method: 'POST',
			data
		});
	}
}

export default AiRuntimeModel;
