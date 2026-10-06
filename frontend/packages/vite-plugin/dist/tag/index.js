"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.createTag = createTag;
const compiler_sfc_1 = require("@vue/compiler-sfc");
const magic_string_1 = __importDefault(require("magic-string"));
function createTag(code, id) {
    if (/\.vue$/.test(id)) {
        let s;
        const str = () => s || (s = new magic_string_1.default(code));
        const { descriptor } = (0, compiler_sfc_1.parse)(code);
        if (!descriptor.script && descriptor.scriptSetup) {
            const res = (0, compiler_sfc_1.compileScript)(descriptor, { id });
            const { name, lang } = res.attrs;
            str().appendLeft(0, `<script lang="${lang}">
					import { defineComponent } from 'vue'
					export default defineComponent({
						name: "${name}"
					})
				<\/script>`);
            return {
                map: str().generateMap(),
                code: str().toString(),
            };
        }
    }
    return null;
}
