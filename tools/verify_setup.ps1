$ErrorActionPreference = 'Continue'
$setup = 'C:\Users\Lingy\vk99screen\eden-tauri\src-tauri\target\release\bundle\nsis\EDEN-VK99II_1.1.0_x64-setup.exe'
$test  = 'C:\Users\Lingy\vk99screen\dist\_installtest'

if (Test-Path $test) { Remove-Item -Recurse -Force $test }
Start-Process -FilePath $setup -ArgumentList '/S', "/D=$test" -Wait
Write-Output '--- installed tree ---'
Get-ChildItem -Recurse $test | ForEach-Object { $_.FullName.Replace($test, '') + '  ' + $_.Length }

Write-Output '--- launch installed exe (no EDEN_ROOT) ---'
$env:EDEN_ROOT = $null
Start-Process -FilePath (Join-Path $test 'eden.exe')
Start-Sleep 40
$found = 0
foreach ($p in 8790..8803) {
    try {
        $r = Invoke-RestMethod -Uri ("http://127.0.0.1:$p/api/ping") -TimeoutSec 2
        if ($r.ok) { $found = $p; break }
    } catch {}
}
Write-Output ("SIDECAR port=" + $found)
Get-Process eden -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
$un = Join-Path $test 'Uninstall.exe'
if (Test-Path $un) { Start-Process -FilePath $un -ArgumentList '/S' -Wait; Write-Output 'uninstaller ran' }
Start-Sleep 3
if (Test-Path $test) { Remove-Item -Recurse -Force $test; Write-Output 'test dir removed' } else { Write-Output 'test dir auto-removed' }
