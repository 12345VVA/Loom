const proxy = {
	'/dev/': {
		target: 'http://127.0.0.1:8000',
		changeOrigin: true,
		rewrite: (path: string) => path.replace(/^\/dev/, '')
	},

	'/prod/': {
		target: 'http://127.0.0.1:8000',
		changeOrigin: true,
		rewrite: (path: string) => path.replace(/^\/prod/, '/api')
	},

	'/uploads/': {
		target: 'http://127.0.0.1:8000',
		changeOrigin: true
	}
};

const value = 'dev';
const host = proxy[`/${value}/`]?.target;

export { proxy, host, value };
