import { BaseService } from '/@/cool';

class AiRuntimeModel extends BaseService {
	private taskService = new BaseService('admin/ai/task');
	// 运行时 AI 调用走 aiapi scope（终端用户调用 AI），与管理端 CRUD 分离
	private runtimeService = new BaseService('aiapi/ai/model');

	constructor() {
		// 管理端 CRUD 继承自 BaseService，走 admin scope（admin/ai/model/*）
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

	submitTask(data: any) {
		return this.taskService.request({
			url: '/submit',
			method: 'POST',
			data
		});
	}

	taskInfo(params: any) {
		return this.taskService.request({
			url: '/info',
			params
		});
	}

	taskPage(data: any) {
		return this.taskService.request({
			url: '/page',
			method: 'POST',
			data
		});
	}

	taskList(data: any) {
		return this.taskService.request({
			url: '/list',
			method: 'POST',
			data
		});
	}

	taskStats(data: any = {}) {
		return this.taskService.request({
			url: '/stats',
			method: 'POST',
			data
		});
	}

	cancelTask(data: any) {
		return this.taskService.request({
			url: '/cancel',
			method: 'POST',
			data
		});
	}

	retryTask(data: any) {
		return this.taskService.request({
			url: '/retry',
			method: 'POST',
			data
		});
	}
}

export default AiRuntimeModel;
