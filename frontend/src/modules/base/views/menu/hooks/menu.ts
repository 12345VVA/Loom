import { ElMessage } from 'element-plus';
import { service } from '/@/cool';

export function useMenu() {
	async function del(router: string) {
		const menus = await service.base.sys.menu.list();
		const item = menus.find(e => e.router == router);
		if (item) {
			await service.base.sys.menu.delete({ ids: [item.id] });
		}
	}

	function create(data: EpsModule): Promise<() => void> {
		return new Promise(async (resolve, reject) => {
			data.viewPath = `modules/${data.module}/views${data.router?.replace(
				`/${data.module}`,
				''
			)}.vue`;

			await del(data.router);

			service.base.sys.menu
				.add({
					type: 1,
					isShow: true,
					keepAlive: true,
					...data,
					api: undefined,
					code: undefined
				})
				.then(res => {
					const perms = data.api?.map(e => {
						const d = {
							type: 2,
							parentId: res.id,
							name: e.summary || e.path,
							perms: [e.path]
						};

						if (e.path == '/update') {
							if (data.api?.find(a => a.path == '/info')) {
								d.perms.push('/info');
							}
						}

						return {
							...d,
							perms: d.perms
								.map(e =>
									(data.prefix?.replace('/admin/', '') + e).replace(/\//g, ':')
								)
								.join(',')
						};
					});

					service.base.sys.menu.add(perms).then(() => {
						resolve(() => {
							service
								.request({
									url: '/__cool_createFile',
									method: 'POST',
									proxy: false,
									data: {
										code: data.code,
										path: data.viewPath
									}
								})
								.then(() => {
									location.reload();
								});
						});
					});
				})
				.catch(err => {
					ElMessage.error(err.message);
					reject();
				});
		});
	}

	return {
		del,
		create
	};
}
