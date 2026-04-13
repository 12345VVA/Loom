/**
 * 特殊字符映射表
 */
export const SAFE_CHAR_MAP: Record<string, string> = {
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
export const SAFE_CHAR_MAP_LOCALE: Record<string, string> = {
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
