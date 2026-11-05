$exe = 'C:\Users\Lingy\vk99screen\eden-tauri\src-tauri\target\release\eden.exe'
(Get-Item $exe).LastWriteTime
Add-Type -AssemblyName System.Drawing
$ic = [System.Drawing.Icon]::ExtractAssociatedIcon($exe)
$bmp = $ic.ToBitmap()
$bmp.Save('C:\Users\Lingy\vk99screen\eden-tauri\tools_exeicon.png')
'EXTRACT-OK'
Start-Process $exe
Start-Sleep 25
Write-Output ("proc=" + (Get-Process eden -ErrorAction SilentlyContinue).Count)
