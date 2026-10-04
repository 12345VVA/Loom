# 将 packages/vite-plugin（vendored 定制版）构建并同步到 node_modules。
#
# 背景：vite 实际加载的是 node_modules 里的 @cool-vue/vite-plugin 安装副本，
# npm install 会把它还原成官方版本、丢掉 EPS 泛型生成器定制——npm install 后重跑本脚本即可。
# 流程规范见 .cursor/rules/eps-dts-generation.mdc。
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot # frontend/
$pkg = Join-Path $root 'packages\vite-plugin'
$target = Join-Path $root 'node_modules\@cool-vue\vite-plugin'

if (-not (Test-Path (Join-Path $pkg 'tsconfig.json'))) {
	throw "未找到 $pkg\tsconfig.json，请在 frontend 仓库内运行"
}
if (-not (Test-Path $target)) {
	throw "未找到 $target，请先 npm install"
}

Push-Location $pkg
try {
	# 构建（仓库内 rollup 管线不可用，直接用 tsc）
	node ..\..\node_modules\typescript\bin\tsc -p tsconfig.json
	if ($LASTEXITCODE -ne 0) {
		throw "tsc 构建失败，退出码 $LASTEXITCODE"
	}

	# 同步产物与类型声明
	Copy-Item -Path (Join-Path $pkg 'dist\*') -Destination (Join-Path $target 'dist\') -Recurse -Force
	Copy-Item -Path (Join-Path $pkg 'types\index.d.ts') -Destination (Join-Path $target 'types\index.d.ts') -Force
}
finally {
	Pop-Location
}

Write-Host ''
Write-Host 'vite-plugin 已同步到 node_modules。' -ForegroundColor Green
Write-Host '注意：必须重启 dev server——存活的旧 dev server 会在下次文件事件用旧插件代码重新覆盖 eps.d.ts。' -ForegroundColor Yellow
