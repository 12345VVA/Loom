declare module "virtual:ctx" {
	const ctx: {
		serviceLang: string;
		modules: string[];
	};

	export { ctx };
}

declare module "virtual:eps" {
	const eps: {
		isUpdate: boolean;
		list: {
			prefix: string;
			api: {
				method: string;
				path: string;
				summary: string;
				dts: {
					[key: string]: string;
				};
				[key: string]: any;
			}[];
			namespace: string;
			name: string;
			module: string;
			columns: {
				comment: string;
				nullable: boolean;
				propertyName: string;
				type: string;
				[key: string]: any;
			}[];
			[key: string]: any;
		}[];
		service: any;
	};

	export { eps };
}

declare module "virtual:demo";
declare module "virtual:svg-register";

declare module "virtual:svg-icons" {
	const svgIcons: string[];
	export { svgIcons };
}
