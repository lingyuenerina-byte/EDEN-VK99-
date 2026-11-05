$src = 'C:\Users\Lingy\vk99screen\dist\EDEN-VK99II幻映_v1.1'
$dst = 'C:\Users\Lingy\vk99screen\dist\EDEN-VK99II幻映_v1.1_win.zip'
Compress-Archive -Path $src -DestinationPath $dst -Force
$item = Get-Item $dst
Write-Output ("ZIP-OK " + $item.Name + " " + [math]::Round($item.Length/1MB,1) + "MB")
