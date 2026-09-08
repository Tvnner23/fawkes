$ErrorActionPreference='Stop'
# Called only after canonical adoption of these exact installed files.
$root=$PSScriptRoot
$binding=Get-Content -Raw -LiteralPath (Join-Path $root 'accepted-binding.json')|ConvertFrom-Json
foreach($name in @('Run-Fawkes-Worker.ps1','Install-Fawkes-Worker-Startup.ps1')){
 if((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $name)).Hash.ToLowerInvariant() -ne $binding.files.$name){throw 'Worker startup hash differs'}
}
$taskName='Fawkes Same Worker Console'
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$exe=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$args='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $root 'Run-Fawkes-Worker.ps1')+'"'
$old=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
function Assert-StartupContract($task){
 $triggers=@($task.Triggers)
 if($triggers.Count -ne 1 -or $triggers[0].CimClass.CimClassName -ne 'MSFT_TaskLogonTrigger' -or -not $triggers[0].Enabled -or $triggers[0].UserId -notin @($user,[Security.Principal.WindowsIdentity]::GetCurrent().User.Value) -or $triggers[0].StartBoundary -or $triggers[0].EndBoundary -or $triggers[0].Delay -notin @($null,'','PT0S')){throw 'Existing automatic logon trigger differs; preserved'}
 foreach($key in @('Enabled','MultipleInstances','ExecutionTimeLimit','StartWhenAvailable','DisallowStartIfOnBatteries','StopIfGoingOnBatteries','RunOnlyIfNetworkAvailable','Hidden')){
  if($task.Settings.$key -ne $settings.$key){throw ('Existing automatic startup setting differs: '+$key)}
 }
}
if($old){
 if($old.Actions.Count -ne 1 -or $old.Actions.Execute -ne $exe -or $old.Actions.Arguments -ne $args -or $old.Principal.UserId -notin @($user,[Security.Principal.WindowsIdentity]::GetCurrent().User.Value) -or $old.Principal.RunLevel -ne 'Limited' -or $old.Principal.LogonType -ne 'Interactive'){throw 'Existing Worker task differs; preserved'}
 Assert-StartupContract $old
}else{
 $action=New-ScheduledTaskAction -Execute $exe -Argument $args
 $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
 $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
 Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings|Out-Null
}
Assert-StartupContract (Get-ScheduledTask -TaskName $taskName)
if((Get-ScheduledTask -TaskName $taskName).State -ne 'Running'){Start-ScheduledTask -TaskName $taskName}
Write-Output 'Automatic same-Worker terminal enabled at Windows sign-in. It waits for the existing owner; no prompt or permission decision supplied. Initial standalone handover still requires that Worker to end its turn and /quit.'
