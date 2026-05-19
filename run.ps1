$ErrorActionPreference = "Stop"
$Python = "C:\Users\marti\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $Python)) {
  throw "No se encontro Python empaquetado en $Python"
}
& $Python ".\app\server.py"

