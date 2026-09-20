$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    $runtimePython = (Get-Command python -ErrorAction Stop).Source
}
$logRoot = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$listening = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process -FilePath $runtimePython -ArgumentList @('-u', 'app.py', 'serve', '--port', '8765') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'server.log') -RedirectStandardError (Join-Path $logRoot 'server-error.log')
}
Start-Process 'http://127.0.0.1:8765'
