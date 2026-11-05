$devs = Get-PnpDevice -Status OK | Where-Object { $_.Class -in 'HIDClass','Keyboard','USB' }
foreach ($d in $devs) {
  $hid = ($d.HardwareId | Where-Object { $_ -match 'VID_' }) -join ','
  if ($d.FriendlyName -match '99|VK|Valkyrie|键盘|Keyboard|HID' -or $hid -match 'VID') {
    "{0} :: {1} :: {2}" -f $d.FriendlyName, $d.Class, $hid
  }
}
