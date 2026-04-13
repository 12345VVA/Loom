import { createPinia } from 'pinia';
import { type App } from 'vue';
import { createModule } from './module';
import { router } from '../router';
import { Loading } from '../utils';
import { createEps } from './eps';
import 'virtual:svg-register';

export async function bootstrap(app: App) {
	// pinia
	app.use(createPinia());

	// 路由
	app.use(router);

	// 模块
	const { eventLoop } = createModule(app);

	// eps
	createEps();

	// 加载
	Loading.set([eventLoop()]);
}
