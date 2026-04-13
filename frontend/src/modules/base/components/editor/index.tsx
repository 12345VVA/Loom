import { defineComponent, h, resolveComponent, ref, reactive, watch } from 'vue';
import { isComponent } from '/@/cool/utils';
import { assign } from 'lodash-es';
import { useI18n } from 'vue-i18n';

export default defineComponent({
	name: 'cl-editor',

	props: {
		name: {
			type: String,
			required: true
		}
	},

	setup(props, { slots, expose }) {
		const Editor = ref();
		const ex = reactive({});
		const { t } = useI18n();

		watch(Editor, v => {
			if (v) {
				assign(ex, v);
			}
		});

		expose(ex);

		return () => {
			return isComponent(props.name) ? (
				h(
					resolveComponent(props.name),
					{
						...props,
						ref: Editor
					},
					slots
				)
			) : (
				<el-input type="textarea" rows={4} placeholder={t('请输入')} {...props} />
			);
		};
	}
});
