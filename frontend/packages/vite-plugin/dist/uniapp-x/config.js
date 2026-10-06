"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SAFE_CHAR_MAP_LOCALE = exports.SAFE_CHAR_MAP = void 0;
/**
 * 特殊字符映射表
 */
exports.SAFE_CHAR_MAP = {
    "[": "-bracket-start-",
    "]": "-bracket-end-",
    "(": "-paren-start-",
    ")": "-paren-end-",
    "{": "-brace-start-",
    "}": "-brace-end-",
    $: "-dollar-",
    "#": "-hash-",
    "!": "-important-",
    "/": "-slash-",
    ":": "-colon-",
};
/**
 * 特殊字符映射表（国际化）
 */
exports.SAFE_CHAR_MAP_LOCALE = {
    "[": "-bracket-start-",
    "]": "-bracket-end-",
    "(": "-paren-start-",
    ")": "-paren-end-",
    "{": "-brace-start-",
    "}": "-brace-end-",
    $: "-dollar-",
    "#": "-hash-",
    "!": "-important-",
    "/": "-slash-",
    ":": "-colon-",
    " ": "-space-",
    "<": "-lt-",
    ">": "-gt-",
    "&": "-amp-",
    "|": "-pipe-",
    "^": "-caret-",
    "~": "-tilde-",
    "`": "-backtick-",
    "'": "-single-quote-",
    ".": "-dot-",
    "?": "-question-",
    "*": "-star-",
    "+": "-plus-",
    "-": "-dash-",
    _: "-underscore-",
    "=": "-equal-",
    "%": "-percent-",
    "@": "-at-",
};
