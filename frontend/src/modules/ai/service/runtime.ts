import { BaseService } from '/@/cool';

class AiRuntimeModel extends BaseService {
	private taskService = new BaseService('admin/ai/task');

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

	streamUrl() {
		return '/aiapi/ai/model/streamChat';
	}

	embedding(data: any) {
		return this.request({ url: '/embedding', method: 'POST', data });
	}

	image(data: any) {
		return this.request({ url: '/image', method: 'POST', data });
	}

	rerank(data: any) {
		return this.request({ url: '/rerank', method: 'POST', data });
	}

	audio(data: any) {
		return this.request({ url: '/audio', method: 'POST', data });
	}

	video(data: any) {
		return this.request({ url: '/video', method: 'POST', data });
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
