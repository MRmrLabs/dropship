$ErrorActionPreference = "Stop"

$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $BundledPython) {
  $Python = $BundledPython
} else {
  $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}

if (-not $Python) {
  throw "No se encontro Python. Instala Python o ejecuta desde un entorno Codex con runtime empaquetado."
}

& $Python (Join-Path $PSScriptRoot "app\server.py")

