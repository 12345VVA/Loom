declare namespace Menu {
	enum Type {
		'目录' = 0,
		'菜单' = 1,
		'权限' = 2
	}

	interface Item {
		id: number;
		parentId: number;
		path: string;
		router?: string;
		viewPath?: string;
		type: Type;
		name: string;
		icon: string;
		badge?: number;
		badgeColor?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
		orderNum: number;
		isShow: number | boolean;
		keepAlive?: number;
		meta?: {
			label?: string;
			keepAlive?: number | boolean;
			iframeUrl?: string;
			isHome?: boolean;
			[key: string]: any;
		};
		children?: Item[];
		component?: any;
		redirect?: string;
		[key: string]: any;
	}

	type List = Item[];
}

declare namespace Process {
	interface Item {
		active: boolean;
		name: string;
		path: string;
		fullPath: string;
		meta: {
			label: string;
			[key: string]: any;
		};
		[key: string]: any;
	}

	type List = Item[];
}

declare interface EpsColumn {
	comment: string;
	length: number;
	nullable: boolean;
	propertyName: string;
	type: string;
	component: string;
	defaultValue: any;
	dict: string[] | string;
}

declare interface EpsApi {
	path: string;
	summary: string;
	method?: string;
	prefix?: string;
	tag?: string;
	dts?: any;
	[key: string]: any;
}

declare interface EpsModule {
	api: EpsApi[];
	columns: EpsColumn[];
	prefix: string;
	router: string;
	module: string;
	fieldEq?: string[];
	keyWordLikeFields?: string[];
	[key: string]: any;
}

declare interface EpsData {
	[key: string]: EpsModule[];
}
