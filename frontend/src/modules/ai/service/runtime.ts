import { BaseService } from '/@/cool';

// 运行时 AI 调用走 aiapi scope（终端用户调用 AI），与管理端 CRUD 分离；
// 管理端任务 CRUD 已回归 EPS（service.ai.task），此处不再重复封装。
class AiRuntimeModel extends BaseService {
	private runtimeService = new BaseService('aiapi/ai/model');

	constructor() {
		super('admin/ai/model');
	}

	chat(data: any) {
		return this.runtimeService.request({
			url: '/chat',
			method: 'POST',
			data
		});
	}

	streamUrl() {
		return '/aiapi/ai/model/streamChat';
	}

	embedding(data: any) {
		return this.runtimeService.request({ url: '/embedding', method: 'POST', data });
	}

	image(data: any) {
		return this.runtimeService.request({ url: '/image', method: 'POST', data });
	}

	rerank(data: any) {
		return this.runtimeService.request({ url: '/rerank', method: 'POST', data });
	}

	audio(data: any) {
		return this.runtimeService.request({ url: '/audio', method: 'POST', data });
	}

	video(data: any) {
		return this.runtimeService.request({ url: '/video', method: 'POST', data });
	}
}

export default AiRuntimeModel;
