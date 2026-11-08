"""Exercise launcher failure paths without starting/stopping real processes."""
import json,subprocess,shutil,unittest
from pathlib import Path

class LocalLaunchTests(unittest.TestCase):
    def invoke(self,scenario,stop=False):
        script=Path(__file__).resolve().parents[1]/'launch-local-research.ps1'
        harness=r'''
$ErrorActionPreference='Stop'
$global:started=$false;$global:stopped=$false;$global:published=$false
function Test-Path { return $true }
function New-Item { }
function Get-Content { return 42 }
function Set-Content { $global:published=$true }
function Remove-Item { }
function Start-Sleep { }
function Invoke-WebRequest { return @{StatusCode=200} }
function Start-Process { $global:started=$true;return [pscustomobject]@{Id=42;HasExited=$false} }
function Get-Process { return [pscustomobject]@{Id=42;HasExited=$false} }
function Stop-Process { $global:stopped=$true }
function Get-CimInstance { return [pscustomobject]@{ProcessId=42;ExecutablePath=(Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe');CommandLine=($global:project+' app.py serve 8771 local-research-dev')} }
'''
        harness+="$global:project='"+str(script.parent).replace("'","''")+"'\n"
        # The launcher is Windows-specific; its mocked profile must also exist
        # when PowerShell tests run on the Linux CI runner.
        harness+="$env:USERPROFILE=$global:project\n"
        if scenario=='denied':harness+="function Get-NetTCPConnection { [CmdletBinding()]param([string]$State,[int]$LocalPort) Write-Error 'query denied' }\n"
        elif scenario=='different-owner':harness+="function Get-NetTCPConnection { return [pscustomobject]@{OwningProcess=43;LocalPort=8771} }\n"
        elif scenario=='owned-stop':
            harness+="function Get-NetTCPConnection { if(-not $global:stopped){return [pscustomobject]@{OwningProcess=42;LocalPort=8771}} }\nfunction Stop-Process { param([int]$Id,[switch]$Force) if(-not $Force){throw 'cross-account process requires Force'} $global:stopped=$true }\n"
        else:harness+="function Get-NetTCPConnection { if($global:started){return [pscustomobject]@{OwningProcess=43;LocalPort=8771}} }\n"
        harness+="try { & '"+str(script).replace("'","''")+"' "+('-Stop' if stop else '-NoBrowser')+" | Out-Null } catch {}\n"
        harness+="@{started=$global:started;stopped=$global:stopped;published=$global:published} | ConvertTo-Json -Compress"
        result=subprocess.run([shutil.which('pwsh') or 'powershell','-NoProfile','-Command',harness],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout.strip())
    def test_permission_denial_does_not_start_duplicate(self):self.assertFalse(self.invoke('denied')['started'])
    def test_stop_refuses_pid_that_does_not_own_listener(self):self.assertFalse(self.invoke('different-owner',stop=True)['stopped'])
    def test_readiness_does_not_publish_pid_of_wrong_listener(self):self.assertFalse(self.invoke('wrong-readiness')['published'])
    def test_verified_owned_process_is_stopped_without_owner_prompt(self):self.assertTrue(self.invoke('owned-stop',stop=True)['stopped'])

if __name__=='__main__':unittest.main()
