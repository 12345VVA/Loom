import { config } from '/@/config';
import { request } from './request';
import { AxiosRequestConfig } from 'axios';

export class BaseService {
	namespace?: string;

	constructor(namespace?: string) {
		if (namespace) {
			this.namespace = namespace;
		}
	}

	// 发送请求
	async request(options: AxiosRequestConfig = {}) {
		let url = options.url;

		if (url && url.indexOf('http') < 0) {
			if (this.namespace) {
				url = this.namespace + url;
			}

			if (options.proxy !== false) {
				url = config.baseUrl + '/' + url;
			}
		}

		return request({
			...options,
			url
		});
	}

	// 获取列表
	async list(data: unknown) {
		return this.request({
			url: '/list',
			method: 'POST',
			data
		});
	}

	// 分页查询
	async page(data: unknown) {
		return this.request({
			url: '/page',
			method: 'POST',
			data
		});
	}

	// 获取信息
	async info(params: unknown) {
		return this.request({
			url: '/info',
			params
		});
	}

	// 更新数据
	async update(data: unknown) {
		return this.request({
			url: '/update',
			method: 'POST',
			data
		});
	}

	// 删除数据
	async delete(data: unknown) {
		return this.request({
			url: '/delete',
			method: 'POST',
			data
		});
	}

	// 添加数据
	async add(data: unknown) {
		return this.request({
			url: '/add',
			method: 'POST',
			data
		});
	}
}
