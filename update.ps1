$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    $runtimePython = (Get-Command python -ErrorAction Stop).Source
}
$env:PYTHONUTF8 = '1'
Push-Location -LiteralPath $projectRoot
try {
    & $runtimePython -u app.py update
    if ($LASTEXITCODE -ne 0) { throw '行情更新失敗，請查看工具中的更新狀態。上一份完整快照已保留。' }
} finally {
    Pop-Location
}
