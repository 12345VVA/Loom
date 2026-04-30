param(
	[switch]$E2E,
	[switch]$Coverage
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backendPython = Join-Path $root 'backend\venv\Scripts\python.exe'
if (-not (Test-Path $backendPython)) {
	$backendPython = 'python'
}

Push-Location (Join-Path $root 'backend')
try {
	if ($Coverage) {
		& $backendPython -c "import pytest_cov" 2>$null
		if ($LASTEXITCODE -ne 0) {
			throw "Coverage requires pytest-cov. Run: cd backend; $backendPython -m pip install -r requirements-dev.txt"
		}
		& $backendPython -m pytest --cov=app --cov-report=term-missing
	} else {
		& $backendPython -m pytest
	}
} finally {
	Pop-Location
}

Push-Location (Join-Path $root 'frontend')
try {
	npm run type-check
	npm run build
	npm run test:unit

	if ($E2E) {
		npm run test:e2e
	}
} finally {
	Pop-Location
}
