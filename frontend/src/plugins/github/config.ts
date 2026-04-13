import { type ModuleConfig } from '/@/cool';

export default (): ModuleConfig => {
	return {
		toolbar: {
			component: import('./components/code.vue')
		}
	};
};
