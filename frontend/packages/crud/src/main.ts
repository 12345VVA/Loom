import { createApp } from "vue";
import App from "./App.vue";
import { Crud, locale } from "./entry";
// import Crud, { locale } from "../dist/index.umd";
// import "../dist/index.css";

import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

const app = createApp(App);

app.use(ElementPlus)
	.use(Crud, {
		dict: {
			sort: {
				prop: "order",
				order: "sort"
			},
			label: locale["zh-cn"]
		},
		style: {
			// size: "default"
		},
		render: {
			autoHeight: true
		}
	})
	.mount("#app");
