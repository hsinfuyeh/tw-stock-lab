param([switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) { $runtimePython = (Get-Command python -ErrorAction Stop).Source }
$logRoot = Join-Path $projectRoot 'logs\local-research'
$dataRoot = Join-Path $projectRoot 'data\local-research-dev'
$pidFile = Join-Path $logRoot 'server.pid'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
function Get-ResearchListeners {
    try { return @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq 8771) }
    catch { throw '無法核對連接埠狀態，拒絕啟動或停止。請在一般使用者 PowerShell 執行。' }
}
$listener = @(Get-ResearchListeners)
$savedServerId = if (Test-Path -LiteralPath $pidFile) { [int](Get-Content -LiteralPath $pidFile) } else { 0 }
$ownedProcess = if ($savedServerId) { Get-CimInstance Win32_Process -Filter "ProcessId=$savedServerId" -ErrorAction Stop } else { $null }
$isOwned = $ownedProcess -and $ownedProcess.ExecutablePath -eq $runtimePython -and $ownedProcess.CommandLine.Contains($projectRoot) -and $ownedProcess.CommandLine.Contains('8771') -and $ownedProcess.CommandLine.Contains('local-research-dev')
if ($Stop) {
    if ($listener.Count -and ($listener.Count -ne 1 -or $listener[0].OwningProcess -ne $savedServerId)) { throw 'PID 與連接埠程序不符，拒絕停止。' }
    if ($isOwned) {
        Stop-Process -Id $savedServerId -Force -ErrorAction Stop
        for ($attempt=0; $attempt -lt 30; $attempt++) {
            if (-not @(Get-ResearchListeners).Count) { break }
            Start-Sleep -Milliseconds 200
        }
        if (@(Get-ResearchListeners).Count) { throw '連接埠仍被占用，未確認伺服器已停止。' }
        Remove-Item -LiteralPath $pidFile
    }
    elseif ($savedServerId) { throw 'PID 已過期或屬於其他程序，拒絕停止。' }
    Write-Output '本機研究伺服器已停止。'
    exit
}
if ($listener) {
    if (-not $isOwned -or @($listener.OwningProcess | Select-Object -Unique).Count -ne 1 -or $listener[0].OwningProcess -ne $savedServerId) { throw '8771 已被其他服務占用，請先排除連接埠衝突。' }
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $dataRoot 'research.sqlite3'))) {
        & $runtimePython -X utf8 (Join-Path $projectRoot 'scripts\seed_local_research.py') --source (Join-Path $projectRoot 'dist') --destination $dataRoot
        if ($LASTEXITCODE -ne 0) { throw '既有快照匯入失敗，未啟動伺服器。' }
    }
    $serverProcess = Start-Process -FilePath $runtimePython -ArgumentList @('-X','utf8','-u',('"'+(Join-Path $projectRoot 'app.py')+'"'),'serve','--port','8771','--data-dir',('"'+$dataRoot+'"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'server.log') -RedirectStandardError (Join-Path $logRoot 'server-error.log')
    $ready = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        $liveProcess=Get-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue
        if (-not $liveProcess -or $liveProcess.HasExited) { throw '新伺服器已退出，未保存 PID；請查看錯誤日誌。' }
        $newListener=@(Get-ResearchListeners)
        if ($newListener.Count -and ($newListener.Count -ne 1 -or $newListener[0].OwningProcess -ne $serverProcess.Id)) { throw '連接埠由其他程序持有，未保存新 PID。' }
        try { if ($newListener.Count -eq 1) { $response=Invoke-WebRequest 'http://127.0.0.1:8771/api/job' -UseBasicParsing; if ($response.StatusCode -eq 200) { $ready=$true; break } } } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw '伺服器未成功啟動，請查看 logs/local-research/server-error.log。' }
    Set-Content -LiteralPath $pidFile -Value $serverProcess.Id
}
Write-Output '本機預覽：http://127.0.0.1:8771（資料目錄 data/local-research-dev）'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8771' }
