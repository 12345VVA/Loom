import { defineComponent } from "vue";

export default defineComponent({
	name: "cl-error-message",

	props: {
		title: String
	},

	setup(props) {
		return () => {
			return <div class="cl-error-message">
				{props.title}
			</div>;
		};
	}
});
